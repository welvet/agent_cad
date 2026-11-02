"""FreeCAD worker that only opens existing CAD and renders a viewport."""
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

import FreeCAD as App
import Part

from render import render_views, validate_options


def main(job_path):
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    output = Path(job["output"])
    started = time.monotonic()
    doc = None
    try:
        names = None if job["view"] == "all" else [job["view"]]
        validate_options(job["resolution"], names, job["region"])
        cad_file = Path(job["cad_file"])
        if cad_file.suffix.lower() == ".fcstd":
            doc = App.openDocument(str(cad_file))
            obj = doc.getObject("Root")
            if obj is None:
                raise ValueError("FCStd must contain a Root object; use the exported STEP instead")
            shape = obj.Shape.copy()
        else:
            shape = Part.read(str(cad_file))
        if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1:
            raise ValueError("inspection expects one valid CAD solid")
        views = render_views(shape, output, job["resolution"], names, job["region"])
        result = {"ok": True, "cad_file": str(cad_file), "rebuilt": False,
                  "cad_sha256": hashlib.sha256(cad_file.read_bytes()).hexdigest(),
                  "run_directory": str(output), "views": views,
                  "contact_sheet": str(output/"views.png"),
                  "framing": json.loads((output/"framing.json").read_text(encoding="utf-8")),
                  "seconds": round(time.monotonic()-started, 2)}
    except Exception as exc:
        result = {"ok": False, "phase": "inspect", "error": str(exc),
                  "error_type": type(exc).__name__, "run_directory": str(output),
                  "traceback": traceback.format_exc()}
    finally:
        if doc is not None:
            App.closeDocument(doc.Name)
    (output/"result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
