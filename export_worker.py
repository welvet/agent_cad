"""Only invoked by the separate approval-bound export command."""
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

import FreeCAD as App
import Part


def main(job_path):
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    output = Path(job["output"])
    doc = None
    started = time.monotonic()
    try:
        cad = Path(job["cad_file"])
        if not job.get("approval") or hashlib.sha256(cad.read_bytes()).hexdigest() != job["cad_sha256"]:
            raise ValueError("approval or approved CAD hash is invalid")
        doc = App.openDocument(str(cad))
        shape = doc.getObject("Root").Shape
        step = output/"model.step"
        candidate = output/"candidate.step"
        shape.exportStep(str(candidate))
        check = Part.read(str(candidate))
        if not check.isValid() or len(check.Solids) != 1:
            raise ValueError("STEP round trip is not one valid solid")
        if abs(check.Volume-shape.Volume) > max(1e-5, shape.Volume*1e-7):
            raise ValueError("STEP round trip changed the volume")
        candidate.replace(step)
        result = {"ok": True, "revision": job["revision"], "step": str(step),
                  "approved": True, "step_round_trip": "passed", "valid": True,
                  "solid_count": 1, "seconds": round(time.monotonic()-started, 2)}
    except Exception as exc:
        result = {"ok": False, "phase": "export", "error": str(exc), "traceback": traceback.format_exc()}
    finally:
        if doc is not None:
            App.closeDocument(doc.Name)
    (output/"result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
