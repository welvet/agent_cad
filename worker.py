"""Executed by FreeCAD's bundled Python, isolated from the MCP interpreter."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import traceback

print("Worker starting", flush=True)
import FreeCAD as App
import Part

import cad_tools as cad
from render import render_views
print("CAD runtime loaded", flush=True)


def main(job_path):
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    output = Path(job["output"])
    result_path = output / "result.json"
    started = time.monotonic()
    phase = "execute"
    logs = io.StringIO()
    try:
        print("Executing model", flush=True)
        source = Path(job["snapshot"]).read_text(encoding="utf-8")
        namespace = dict(cad.PUBLIC, __name__="__cad_model__", __file__=job["source"])
        # FreeCAD diagnostics go to worker.log, not the MCP's stdio transport.
        with contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
            exec(compile(source, job["source"], "exec"), namespace)
        root = namespace.get("root")
        if not isinstance(root, cad.Solid):
            raise cad.ModelError("assign exactly one final solid to root, e.g. root = box(10, 10, 10)")
        phase = "validate"
        shape = cad._valid(root.shape, "root")
        # Spline control-point bounds can extend well beyond the actual surface.
        bounds = shape.optimalBoundingBox()
        for axis in "XYZ":
            low, high = getattr(bounds, axis+"Min"), getattr(bounds, axis+"Max")
            if low < -1e-6 or high > 256+1e-6:
                raise cad.ModelError(f"root {axis} bounds [{low:.3f}, {high:.3f}] exceed workspace 0..256 mm; move or resize root")
        phase = "render"
        print("Rendering views", flush=True)
        previews = render_views(shape, output)
        phase = "save"
        print("Saving native working document", flush=True)
        doc = App.newDocument("AgentCAD")
        obj = doc.addObject("Part::Feature", "Root")
        obj.Label = Path(job["source"]).stem
        obj.Shape = shape
        obj.addProperty("App::PropertyString", "SourcePath", "Model").SourcePath = job["source"]
        obj.addProperty("App::PropertyString", "SourceSHA256", "Model").SourceSHA256 = hashlib.sha256(source.encode()).hexdigest()
        obj.addProperty("App::PropertyString", "ModelScript", "Model").ModelScript = source
        doc.recompute()
        fcstd = output / "model.FCStd"
        doc.saveAs(str(fcstd))
        edges = []
        for i, edge in enumerate(shape.Edges, 1):
            center = edge.CenterOfMass
            # Fillet corners can contain degenerate edges with no curve object.
            try:
                curve_type = type(edge.Curve).__name__
            except TypeError:
                curve_type = "Degenerate"
            edges.append({"id": f"E{i}", "type": curve_type,
                          "center_mm": [round(center.x, 1), round(center.y, 1), round(center.z, 1)],
                          "length_mm": round(edge.Length, 1)})
        result = {
            "ok": True, "source": job["source"], "source_sha256": obj.SourceSHA256,
            "run_directory": str(output), "freecad": str(fcstd), "status": "draft",
            "exported": False,
            "views": previews, "contact_sheet": str(output/"views.png"),
            "framing": json.loads((output/"framing.json").read_text(encoding="utf-8")),
            "solid_count": len(shape.Solids), "valid": shape.isValid(),
            "size_mm": [round(bounds.XLength, 1), round(bounds.YLength, 1), round(bounds.ZLength, 1)],
            "bounds_mm": {a: [round(getattr(bounds, a+"Min"), 1), round(getattr(bounds, a+"Max"), 1)] for a in "XYZ"},
            "volume_mm3": round(shape.Volume, 1), "edges": edges,
            "seconds": round(time.monotonic()-started, 2), "freecad_version": ".".join(App.Version()[:3]),
        }
        App.closeDocument(doc.Name)
    except Exception as exc:
        frames = traceback.extract_tb(exc.__traceback__)
        model_frames = [f for f in frames if f.filename == job["source"]]
        line = model_frames[-1].lineno if model_frames else getattr(exc, "lineno", None)
        result = {"ok": False, "phase": phase, "error": str(exc), "error_type": type(exc).__name__,
                  "source": job["source"], "line": line,
                  "run_directory": str(output), "traceback": traceback.format_exc()}
    (output/"model.log").write_text(logs.getvalue(), encoding="utf-8")
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
