"""Run with FreeCAD's bundled Python; verifies geometric behavior, not mocks."""
from pathlib import Path
import math
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cad_tools as c


class GeometryTests(unittest.TestCase):
    def assertSolid(self, value):
        self.assertTrue(value.shape.isValid())
        self.assertEqual(len(value.shape.Solids), 1)

    def test_rounded_cube_blind_hole(self):
        rounded = c.box(10, 10, 10).fillet(0.5)
        final = rounded.hole(2, 5, at=(5, 5, 10))
        self.assertSolid(final)
        self.assertAlmostEqual(rounded.shape.Volume-final.shape.Volume, math.pi*5, places=6)
        self.assertAlmostEqual(final.shape.BoundBox.ZLength, 10, places=6)

    def test_boolean_tools_and_moves(self):
        root = c.box(10, 10, 10).add(c.box(2, 2, 2, at=(9, 4, 4)))
        self.assertAlmostEqual(root.shape.Volume, 1004, places=6)
        root = root.intersect(c.box(10, 10, 10)).move((10, 10, 0)).rotate(90, at=(10, 10, 0))
        self.assertSolid(root)
        self.assertAlmostEqual(root.shape.Volume, 1000, places=6)

    def test_cone_sphere_tube_chamfer(self):
        self.assertAlmostEqual(c.cone(10, 0, 12).shape.Volume, math.pi*25*4, places=5)
        self.assertAlmostEqual(c.sphere(10).shape.Volume, 4/3*math.pi*125, places=5)
        self.assertAlmostEqual(c.tube(10, 1, 12).shape.Volume, math.pi*(25-16)*12, places=5)
        self.assertLess(c.box(10, 10, 10).chamfer(0.5).shape.Volume, 1000)

    def test_profile_planes(self):
        for plane, axis, size in (("XY", "Z", (3, 4, 5)), ("XZ", "Y", (3, 5, 4)),
                                  ("YZ", "X", (5, 3, 4))):
            solid = c.extrude(c.rectangle(3, 4, at=(10, 10, 10), plane=plane), 5, axis)
            self.assertSolid(solid)
            b = solid.shape.BoundBox
            for actual, expected in zip((b.XLength, b.YLength, b.ZLength), size):
                self.assertAlmostEqual(actual, expected, places=6)

    def test_loft_and_revolve(self):
        solid = c.loft([c.circle(30, at=(20, 20, 0)), c.circle(10, at=(20, 20, 35))])
        self.assertSolid(solid)
        self.assertAlmostEqual(solid.shape.Volume, math.pi*35*(225+75+25)/3, places=4)
        profile = c.rectangle(2, 5, at=(3, 0, 0), plane="XZ")
        solid = c.revolve(profile)
        self.assertSolid(solid)
        self.assertAlmostEqual(solid.shape.Volume, math.pi*(25-9)*5, places=5)

    def test_arc_outline_and_sweep(self):
        profile = c.wire(
            c.line((0, 0, 0), (10, 0, 0)),
            c.arc((10, 0, 0), (15, 5, 0), (10, 10, 0)),
            c.line((10, 10, 0), (0, 10, 0)),
            c.line((0, 10, 0), (0, 0, 0)), closed=True,
        )
        self.assertAlmostEqual(c.extrude(profile, 5).shape.Volume, (100+math.pi*25/2)*5, places=5)
        solid = c.sweep(c.circle(2, at=(10, 10, 0)), c.line((10, 10, 0), (10, 10, 15)))
        self.assertSolid(solid)
        self.assertAlmostEqual(solid.shape.Volume, math.pi*15, places=5)

    def test_spline_profiles(self):
        path = c.curve([(0, 0, 0), (0, 2, 5), (0, 0, 10)])
        self.assertGreater(path.wire.Length, 10)
        profile = c.curve([(10, 0, 0), (15, 5, 0), (10, 10, 0), (5, 5, 0)], closed=True)
        self.assertSolid(c.extrude(profile, 3))

    def test_linear_grid_and_radial_arrays(self):
        tool = c.cylinder(2, 5, at=(5, 5, 10), axis="-Z")
        tools = c.array(tool, count=(2, 2, 1), step=(10, 10, 0))
        self.assertEqual(len(tools), 4)
        root = c.box(20, 20, 10).subtract(tools)
        self.assertAlmostEqual(root.shape.Volume, 4000-20*math.pi, places=5)
        linear = c.array(c.box(2, 2, 2), count=3, step=(1, 1, 0))
        self.assertSolid(linear[0].merge(linear[1:]))
        radial = c.radial_array(c.cylinder(2, 5, at=(15, 10, 10), axis="-Z"),
                                count=7, at=(10, 10, 0))
        root = c.box(20, 20, 10).subtract(radial)
        self.assertAlmostEqual(root.shape.Volume, 4000-35*math.pi, places=5)
        arc = c.radial_array(c.box(1, 1, 1, at=(10, 0, 0)), 3, angle=180)
        self.assertAlmostEqual(arc[-1].shape.BoundBox.XMin, -11, places=6)

    def test_pipe_automatic_orientation_and_wall(self):
        for end in ((20, 10, 10), (10, 20, 10), (10, 10, 20)):
            solid = c.pipe(4, c.line((10, 10, 10), end), wall=1)
            self.assertSolid(solid)
            self.assertAlmostEqual(solid.shape.Volume, math.pi*3*10, places=5)
        path = c.arc((10, 0, 0), (0, 10, 0), (-10, 0, 0))
        solid = c.pipe(2, path)
        self.assertSolid(solid)
        self.assertAlmostEqual(solid.shape.Volume, math.pi**2*10, places=5)
        path = c.spline([(10,10,0), (10,10,10), (15,10,20)])
        self.assertSolid(c.pipe(2, path, wall=0.5))

    def test_mirror_scale_and_profile_offset(self):
        root = c.box(10, 5, 3, at=(5, 5, 0)).mirror("YZ", at=(20, 0, 0))
        self.assertAlmostEqual(root.shape.BoundBox.XMin, 25, places=6)
        root = root.scale(2, at=(25, 5, 0))
        self.assertAlmostEqual(root.shape.Volume, 150*8, places=5)
        profile = c.rectangle(10, 5).offset(1, corners="sharp")
        solid = c.extrude(profile, 3)
        self.assertAlmostEqual(solid.shape.Volume, 12*7*3, places=6)
        profile = c.circle(10).offset(-1)
        self.assertAlmostEqual(c.extrude(profile, 3).shape.Volume, math.pi*16*3, places=5)
        p = c.polyline([(0,0,0),(10,0,0),(10,5,0),(0,5,0)], closed=True)
        self.assertAlmostEqual(c.extrude(p, 3).shape.Volume, 150, places=6)

    def test_array_pipe_and_offset_errors(self):
        tool = c.box(1,1,1)
        for call in (
            lambda: c.array(tool, 0, (1,0,0)),
            lambda: c.array(tool, True, (1,0,0)),
            lambda: c.array(tool, 3, (0,0,0)),
            lambda: c.array(tool, (2,2,1), (1,0,0)),
            lambda: c.array(tool, 1001, (1,0,0)),
            lambda: c.radial_array(tool, 3, angle=360.1),
            lambda: c.pipe(4, c.line((0,0,0),(0,0,10)), wall=2),
            lambda: c.rectangle(10,5).offset(1, corners="other"),
            lambda: tool.subtract([]),
            lambda: tool.merge([]),
        ):
            with self.subTest(call=call), self.assertRaises(c.ModelError):
                call()

    def test_parameter_and_topology_errors(self):
        for call in (
            lambda: c.box(1.01, 1, 1),
            lambda: c.box(float("nan"), 1, 1),
            lambda: c.box(True, 1, 1),
            lambda: c.box(0, 1, 1),
            lambda: c.tube(10, 5, 10),
            lambda: c.box(10, 10, 10).cut(c.box(1, 1, 1, at=(20, 20, 20))),
            lambda: c.box(10, 10, 10).add(c.box(1, 1, 1, at=(20, 20, 20))),
            lambda: c.box(10, 10, 10).cut(c.box(2, 12, 12, at=(4, -1, -1))),
            lambda: c.box(10, 10, 10).fillet(0.5, edges=["E999"]),
        ):
            with self.subTest(call=call), self.assertRaises(c.ModelError):
                call()


if __name__ == "__main__":
    unittest.main(verbosity=2)
