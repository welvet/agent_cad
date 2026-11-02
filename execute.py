"""Shared CLI/MCP execution path; discovers and starts headless FreeCAD."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid


HERE = Path(__file__).resolve().parent


def find_freecad_python():
    configured = os.environ.get("AGENT_CAD_FREECAD_PYTHON")
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.is_file():
            raise RuntimeError(f"AGENT_CAD_FREECAD_PYTHON does not exist: {path}")
        return path
    candidates = []
    if os.name == "nt":
        for base in (Path(os.environ.get("ProgramFiles", "C:/Program Files")),
                     Path(os.environ.get("LOCALAPPDATA", str(Path.home())))):
            candidates.extend(sorted(base.glob("FreeCAD*/bin/python.exe"), reverse=True))
            candidates.extend(sorted(base.glob("Programs/FreeCAD*/bin/python.exe"), reverse=True))
    executable = shutil.which("freecad") or shutil.which("FreeCAD")
    if executable:
        base = Path(executable).resolve().parent
        candidates.extend([base/"python.exe", base/"python3"])
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("FreeCAD bundled Python not found. Set AGENT_CAD_FREECAD_PYTHON to its full executable path.")


def _run_worker(freecad_python, worker, job_path, output, timeout):
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    # An inherited virtualenv/PYTHONPATH must not replace FreeCAD's own modules.
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with (output/"worker.log").open("w", encoding="utf-8") as log:
        try:
            process = subprocess.run([str(freecad_python), str(HERE/worker), str(job_path)],
                                     cwd=str(HERE), env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                     timeout=timeout, creationflags=flags)
        except subprocess.TimeoutExpired:
            job = json.loads(job_path.read_text(encoding="utf-8"))
            result = {"ok": False, "phase": "timeout", "error": f"CAD execution exceeded {timeout:g} seconds",
                      "source": job.get("source", job.get("cad_file")), "run_directory": str(output)}
            (output/"result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            return result
    result_path = output/"result.json"
    if not result_path.exists():
        return {"ok": False, "phase": "worker", "error": "FreeCAD worker exited without a result",
                "exit_code": process.returncode, "run_directory": str(output),
                "log": (output/"worker.log").read_text(encoding="utf-8", errors="replace")[-6000:]}
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if process.returncode != 0 and result.get("ok"):
        return {"ok": False, "phase": "worker", "error": "worker failed after generating output",
                "exit_code": process.returncode, "run_directory": str(output)}
    return result


def execute_cad(file_path: str, timeout: float = 120, project_dir=None, live=True) -> dict:
    try:
        source = Path(file_path).expanduser().resolve()
        if not source.is_file():
            raise ValueError(f"model file does not exist: {source}")
        if source.suffix.lower() != ".py":
            raise ValueError("model must be a Python .py file (recommended: name.cad.py)")
        source_text = source.read_text(encoding="utf-8-sig")
        from project import project_folder, publish_build, record_failure
        project = project_folder(source, project_dir)
        freecad_python = find_freecad_python()
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")+"_"+uuid.uuid4().hex[:8]
        output = project / "history" / run_id
        output.mkdir(parents=True)
        snapshot = output / "source.cad.py"
        snapshot.write_text(source_text, encoding="utf-8")
        job = {"source": str(source), "snapshot": str(snapshot), "output": str(output)}
        job_path = output/"job.json"
        job_path.write_text(json.dumps(job), encoding="utf-8")
        result = _run_worker(freecad_python, "worker.py", job_path, output, timeout)
        if result["ok"]:
            result = publish_build(project, source, source_text, result)
            if live:
                from live import open_live
                result["live"] = open_live(project)
        else:
            record_failure(project, result)
        return result
    except Exception as exc:
        return {"ok": False, "phase": "setup", "error": str(exc), "error_type": type(exc).__name__}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build one CAD model and render four views")
    parser.add_argument("file_path")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--project-dir")
    parser.add_argument("--no-live", action="store_true")
    args = parser.parse_args()
    result = execute_cad(args.file_path, args.timeout, args.project_dir, not args.no_live)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
