"""Approval-bound STEP export. Draft builds never call this module."""
import hashlib
import json
from pathlib import Path

from execute import find_freecad_python, _run_worker
from project import atomic_json, project_folder


def reviewed_draft(project_dir, revision, approval):
    project = project_folder(Path(project_dir)/"model.cad.py", project_dir)
    manifest = json.loads((project/"project.json").read_text(encoding="utf-8"))
    if not isinstance(approval, str) or not approval.strip():
        raise ValueError("explicit user approval is required; quote the user's approval in approval")
    if revision != manifest["revision"]:
        raise ValueError("approval revision is not the current draft; review and approve the current revision")
    cad = Path(manifest["freecad"])
    cad_hash = hashlib.sha256(cad.read_bytes()).hexdigest()
    if cad_hash != manifest["freecad_sha256"]:
        raise ValueError("saved CAD changed after review; rebuild and request approval again")
    for source in {Path(manifest["source"]), project/"model.cad.py"}:
        digest = hashlib.sha256(source.read_text(encoding="utf-8-sig").encode()).hexdigest()
        if digest != manifest["source_sha256"]:
            raise ValueError("source changed since this draft; rebuild and review before exporting")
    return project, manifest, cad, cad_hash


def export_cad(project_dir, revision, approval, timeout=120):
    try:
        project, manifest, cad, cad_hash = reviewed_draft(project_dir, revision, approval)
        output = project/"exports"/revision
        output.mkdir(parents=True, exist_ok=True)
        if (output/"model.step").exists():
            raise ValueError("this revision is already exported; existing export is preserved")
        job = {"cad_file": str(cad), "output": str(output), "revision": revision,
               "approval": approval.strip(), "cad_sha256": cad_hash}
        job_path = output/"job.json"
        atomic_json(job_path, job)
        result = _run_worker(find_freecad_python(), "export_worker.py", job_path, output, timeout)
        if result["ok"]:
            atomic_json(output/"approval.json", {"revision": revision, "user_approval": approval.strip(),
                        "cad_sha256": cad_hash, "step": result["step"]})
        return result
    except Exception as exc:
        return {"ok": False, "phase": "approval", "error": str(exc), "error_type": type(exc).__name__}
