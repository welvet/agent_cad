"""Render saved CAD without rerunning its model script or exporting geometry."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

from execute import find_freecad_python, _run_worker


def resolve_cad(file_path):
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"file does not exist: {path}")
    if path.suffix.lower() in (".step", ".stp", ".fcstd"):
        return path
    if path.suffix.lower() == ".json":
        result = json.loads(path.read_text(encoding="utf-8"))
        cad = result.get("freecad") or result.get("step")
        if not result.get("ok") or not cad:
            raise ValueError("result JSON must describe a successful CAD build")
        cad_path = Path(cad)
        if not cad_path.is_absolute():
            cad_path = path.parent/cad_path
        return resolve_cad(cad_path)
    if path.suffix.lower() == ".py":
        digest = hashlib.sha256(path.read_text(encoding="utf-8-sig").encode()).hexdigest()
        candidates = list((path.parent/"history").glob("*/result.json"))
        candidates += list((path.parent/".cad-runs"/path.stem).glob("*/result.json"))
        for candidate in sorted(candidates, key=lambda p: p.parent.name, reverse=True):
            try:
                result = json.loads(candidate.read_text(encoding="utf-8"))
                if result.get("ok") and result.get("source_sha256") == digest:
                    return resolve_cad(result.get("freecad") or result["step"])
            except (ValueError, OSError, KeyError):
                continue
        raise ValueError("no successful build matches this source; call execute_cad first, or inspect a saved STEP")
    raise ValueError("inspect a STEP, FCStd, successful result.json, or previously built .cad.py")


def inspect_cad(file_path, view="isometric", region=None, resolution=1024, timeout=120):
    try:
        if view not in ("top", "front", "right", "isometric", "all"):
            raise ValueError("view must be top, front, right, isometric, or all")
        if isinstance(resolution, bool) or not isinstance(resolution, int) or not 256 <= resolution <= 2048:
            raise ValueError("resolution must be an integer from 256 to 2048")
        cad_file = resolve_cad(file_path)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")+"_"+uuid.uuid4().hex[:8]
        project = next((p for p in cad_file.parents if (p/"project.json").is_file()), None)
        output = project/"history"/"inspections"/run_id if project else cad_file.parent/".cad-inspections"/cad_file.stem/run_id
        output.mkdir(parents=True)
        job_path = output/"job.json"
        job_path.write_text(json.dumps({"cad_file": str(cad_file), "output": str(output),
                                       "view": view, "region": region, "resolution": resolution}), encoding="utf-8")
        result = _run_worker(find_freecad_python(), "inspect_worker.py", job_path, output, timeout)
        if result["ok"] and project:
            from project import atomic_copy, atomic_json
            for name, path in result["views"].items():
                atomic_copy(path, project/"previews"/f"inspect_{name}.png")
            atomic_json(project/"previews"/"last_inspection.json", result)
        return result
    except Exception as exc:
        return {"ok": False, "phase": "setup", "error": str(exc), "error_type": type(exc).__name__}
