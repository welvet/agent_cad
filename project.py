"""Project-local working files and immutable build revisions."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid


WORKSPACE = Path(os.environ.get("AGENT_CAD_WORKSPACE", str(Path(__file__).resolve().parent.parent))).resolve()


def project_folder(source, specified=None):
    project = Path(specified).expanduser().resolve() if specified else Path(source).resolve().parent
    if project == WORKSPACE or not project.is_relative_to(WORKSPACE):
        raise ValueError(f"use a project subdirectory inside {WORKSPACE}; never write models at the workspace root")
    project.mkdir(parents=True, exist_ok=True)
    return project


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def atomic_copy(source, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name+"."+uuid.uuid4().hex+".tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, destination)


def publish_build(project, source, source_text, result):
    revision = Path(result["run_directory"])
    working = project/"model.FCStd"
    atomic_copy(result["freecad"], working)
    # Keep the requested canonical source without changing the user's actual file.
    canonical = project/"model.cad.py"
    if canonical.resolve() != Path(source).resolve():
        atomic_copy(revision/"source.cad.py", canonical)
    preview_dir = project/"previews"
    for path in [*result["views"].values(), result["contact_sheet"], str(revision/"framing.json")]:
        atomic_copy(path, preview_dir/Path(path).name)
    result.update({"project_dir": str(project), "working_file": str(working),
                   "preview_directory": str(preview_dir), "revision": revision.name,
                   "review_required": True})
    atomic_json(revision/"result.json", result)
    manifest = {"version": 1, "revision": revision.name, "status": "draft",
                "source": str(Path(source).resolve()), "source_sha256": result["source_sha256"],
                "canonical_source_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
                "freecad": result["freecad"], "working_file": str(working),
                "freecad_sha256": hashlib.sha256(Path(result["freecad"]).read_bytes()).hexdigest(),
                "result": str(revision/"result.json")}
    # This commit marker is what the GUI watches. It always points to immutable CAD.
    atomic_json(project/"project.json", manifest)
    return result


def record_failure(project, result):
    atomic_json(project/"last_error.json", result)
