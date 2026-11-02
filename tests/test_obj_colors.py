"""Real CAD/mesh checks for color boundaries, topology, and OBJ material output."""
from pathlib import Path
import json
import math
import sys
import tempfile
import unittest
import zipfile

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import FreeCAD as App
import Part
from obj_colors import load_colors,colored_mesh
from execute import execute_cad
from colored_export import export_colored_obj


class ColorTests(unittest.TestCase):
    def setUp(self):
        folder=HERE/"tests"/".test-runs"
        folder.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=folder)
        self.project=Path(self.temp.name)
        self.colors=self.project/"colors.py"

    def tearDown(self):
        self.temp.cleanup()

    def rules(self,text):
        self.colors.write_text(text,encoding="utf-8")
        return load_colors(self.colors)

    def test_boundary_mesh_keeps_area_volume_and_closed_edges(self):
        palette,color,planes=self.rules(
            "PALETTE={'Blue':'#0000FF','Red':(1,0,0)}\n"
            "SPLIT_PLANES={'x':[4]}\n"
            "def color_at(x,y,z): return 'Blue' if x<4 else 'Red'\n")
        vertices,groups,stats=colored_mesh(Part.makeBox(10,10,10),palette,color,planes)
        self.assertEqual(stats["mesh_edge_anomalies"],0)
        self.assertEqual(stats["size_mm"],[10,10,10])
        area=volume=0
        for material,faces in groups.items():
            self.assertTrue(faces)
            for face in faces:
                a,b,c=(App.Vector(*vertices[i-1]) for i in face)
                area+=(b-a).cross(c-a).Length/2
                volume+=a.dot(b.cross(c))/6
                for vertex in (a,b,c):
                    self.assertTrue(vertex.x<=4+1e-7 if material=="Blue" else vertex.x>=4-1e-7)
        self.assertAlmostEqual(area,600,places=5)
        self.assertAlmostEqual(abs(volume),1000,places=5)

    def test_bad_color_rules(self):
        for text in ("PALETTE={}\n", "PALETTE={'bad name':'#FFFFFF'}\n",
                     "PALETTE={'White':(2,0,0)}\n", "PALETTE={'A':'#fff'}\n",
                     "PALETTE={'A':'#FFFFFF','B':'#000000'}\n",
                     "PALETTE={'A':'#FFFFFF'}\nSPLIT_PLANES={'x':[0.01]}\n"):
            with self.subTest(text=text),self.assertRaises(ValueError):
                self.rules(text)
        palette,color,planes=self.rules("PALETTE={'A':'#FFFFFF'}\ndef color_at(x,y,z): return 'missing'\n")
        with self.assertRaisesRegex(ValueError,"unknown material"):
            colored_mesh(Part.makeBox(1,1,1),palette,color,planes)

    def test_approved_export_files_and_native_unchanged(self):
        source=self.project/"model.cad.py"
        source.write_text("root=box(10,10,10)\n")
        build=execute_cad(str(source),live=False)
        self.assertTrue(build["ok"],build)
        original=Path(build["freecad"]).read_bytes()
        self.rules("PALETTE={'Blue':'#0000FF','Red':'#FF0000'}\nSPLIT_PLANES={'x':[4]}\ndef color_at(x,y,z): return 'Blue' if x<4 else 'Red'\n")
        self.assertFalse(export_colored_obj(str(self.project),build["revision"],"")["ok"])
        result=export_colored_obj(str(self.project),build["revision"],"Synthetic test fixture approval")
        self.assertTrue(result["ok"],result)
        self.assertFalse(result["rebuilt"])
        self.assertEqual(Path(build["freecad"]).read_bytes(),original)
        self.assertEqual(result["mesh_edge_anomalies"],0)
        obj=Path(result["obj"]).read_text()
        mtl=Path(result["mtl"]).read_text()
        self.assertIn("mtllib model.mtl",obj)
        self.assertIn("usemtl Blue",obj)
        self.assertIn("usemtl Red",obj)
        self.assertIn("newmtl Blue",mtl)
        with zipfile.ZipFile(result["zip"]) as archive:
            self.assertEqual(set(archive.namelist()),{"model.obj","model.mtl","README.txt","export_info.json"})
            self.assertIsNone(archive.testzip())
        self.assertFalse(list(self.project.rglob("*.stl")))
        self.assertFalse(list(self.project.rglob("*.step")))
        self.assertFalse(export_colored_obj(str(self.project),build["revision"],"Synthetic test fixture approval")["ok"])


if __name__=="__main__":
    unittest.main(verbosity=2)
