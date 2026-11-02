from pathlib import Path
import tempfile
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from execute import execute_cad
from inspection import resolve_cad, inspect_cad
from exporting import export_cad


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        output = HERE / "tests" / ".test-runs"
        output.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=output)
        self.source = Path(self.temp.name)/"model.cad.py"

    def tearDown(self):
        self.temp.cleanup()

    def run_source(self, text, **kwargs):
        self.source.write_text(text, encoding="utf-8")
        return execute_cad(str(self.source), live=False, **kwargs)

    def test_iteration_and_exports(self):
        first = self.run_source("root = box(10,10,10)\n")
        self.assertTrue(first["ok"], first)
        self.assertFalse(first["exported"])
        self.assertNotIn("step", first)
        self.assertTrue((self.source.parent/"model.FCStd").is_file())
        self.assertTrue((self.source.parent/"previews"/"views.png").is_file())
        self.assertFalse(list(self.source.parent.rglob("*.step")))
        self.assertEqual(resolve_cad(self.source), Path(first["freecad"]))
        second = self.run_source("root = box(10,10,10).hole(2,5,at=(5,5,10))\n")
        self.assertTrue(second["ok"], second)
        self.assertNotEqual(first["run_directory"], second["run_directory"])
        self.assertNotEqual(first["source_sha256"], second["source_sha256"])
        self.assertLess(second["volume_mm3"], first["volume_mm3"])
        self.assertEqual(second["size_mm"], [10,10,10])
        for path in [second["freecad"], *second["views"].values()]:
            self.assertGreater(Path(path).stat().st_size, 100)
        self.assertFalse(list(Path(self.temp.name).rglob("*.stl")))
        failure = self.run_source("root = box(1.01,1,1)\n")
        self.assertFalse(failure["ok"])
        self.assertEqual(failure["line"], 1)
        self.assertNotIn("views", failure)
        self.assertNotIn("step", failure)
        import json
        manifest = json.loads((self.source.parent/"project.json").read_text())
        self.assertEqual(manifest["revision"], second["revision"])
        with self.assertRaisesRegex(ValueError, "no successful build"):
            resolve_cad(self.source)

    def test_errors(self):
        for source, message in (
            ("box(10,10,10)\n", "root"),
            ("root = box(257,1,1)\n", "workspace"),
            ("root = box(1,1,1,at=(-0.1,0,0))\n", "workspace"),
            ("root = box(\n", "never closed"),
            ("root = box(10,10,10).fillet(8)\n", ""),
        ):
            with self.subTest(source=source):
                result = self.run_source(source)
                self.assertFalse(result["ok"], result)
                self.assertIn(message, result["error"])
                self.assertNotIn("views", result)
        missing = execute_cad(str(self.source.with_name("missing.py")))
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["phase"], "setup")

    def test_timeout(self):
        result = self.run_source("while True: pass\n", timeout=2)
        self.assertFalse(result["ok"])
        self.assertEqual(result["phase"], "timeout")

    def test_inspection_validation(self):
        for options in ({"view": "unknown"}, {"resolution": 100}):
            result = inspect_cad(str(self.source), **options)
            self.assertFalse(result["ok"])
            self.assertEqual(result["phase"], "setup")

    def test_approval_bound_fixture_export(self):
        source = "root = box(10,10,10)\n"
        build = self.run_source(source)
        self.assertTrue(build["ok"], build)
        project = str(self.source.parent)
        self.assertFalse(export_cad(project, build["revision"], "")["ok"])
        self.assertFalse(export_cad(project, "older-revision", "fixture approval")["ok"])
        self.source.write_text("root = box(11,10,10)\n")
        self.assertFalse(export_cad(project, build["revision"], "fixture approval")["ok"])
        self.source.write_text(source)
        # Isolated test fixture exercises export; never approves a user project.
        result = export_cad(project, build["revision"], "Automated test fixture approval")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["step_round_trip"], "passed")
        self.assertTrue(Path(result["step"]).is_file())

    def test_curved_pipe_array_and_geometric_bounds(self):
        # The spline's control-point box crosses X=0, but the actual solid does not.
        source = (HERE/"examples"/"arrays_pipe.cad.py").read_text(encoding="utf-8")
        result = self.run_source(source)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["solid_count"], 1)
        self.assertEqual(result["size_mm"][:2], [60, 40])
        self.assertGreater(result["size_mm"][2], 25)
        self.assertGreaterEqual(result["bounds_mm"]["X"][0], 0)
        self.assertFalse(list(Path(self.temp.name).rglob("*.stl")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
