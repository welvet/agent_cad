"""FreeCAD Python: verify framing and fresh geometry rendering at close-up scale."""
from pathlib import Path
import sys
import tempfile
import json
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import FreeCAD
import Part
import numpy as np
from PIL import Image
from render import render_views, view_frame, validate_options


class RenderTests(unittest.TestCase):
    def test_independent_fitting(self):
        shape = Part.makeBox(200, 20, 30)
        output = Path(__file__).parent/".test-runs"
        output.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output) as directory:
            paths = render_views(shape, directory)
            framing = json.loads((Path(directory)/"framing.json").read_text())
            self.assertGreater(framing["right"]["projected_span_pixels"][0], 590)
            self.assertGreater(framing["right"]["projected_span_pixels"][1], 890)
            self.assertGreater(framing["front"]["projected_span_pixels"][0], 920)
            self.assertLess(framing["right"]["mm_per_pixel"], framing["front"]["mm_per_pixel"])
            for path in paths.values():
                with Image.open(path) as image:
                    self.assertEqual(image.size, (1024,1024))
                    pixels = np.array(image)
                    blue = (pixels[:,:,2] > pixels[:,:,0]+10) & (pixels[:,:,0] < 180)
                    self.assertGreater(int(blue.sum()), 1000)

    def test_focus_changes_projection_scale(self):
        full = np.array([[0,0,0],[200,20,30]])
        focus = np.array([[0,0,0],[20,10,10]])
        identity = np.identity(3)
        full_scale, *_ = view_frame(full, identity, 1024)
        close_scale, *_ = view_frame(focus, identity, 1024)
        self.assertGreater(close_scale, full_scale*5)

    def test_invalid_viewport_options(self):
        for args in ((100, None, None), (True,None,None), (1024,["bad"],None),
                     (1024,None,[[0,0,0],[0,1,1]]), (1024,None,[[0,0,0],[1.01,1,1]])):
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_options(*args)


if __name__ == "__main__":
    unittest.main(verbosity=2)
