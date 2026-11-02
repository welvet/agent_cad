"""Launch/reuse a project-specific FreeCAD viewer with a polling macro."""
import json
import os
from pathlib import Path
import subprocess
import time

from execute import HERE, find_freecad_python
from project import atomic_json


def open_live(project):
    project = Path(project).resolve()
    heartbeat = project/"live_status.json"
    if heartbeat.exists():
        try:
            status = json.loads(heartbeat.read_text(encoding="utf-8"))
            if time.time()-status.get("heartbeat", 0) < 5:
                return {"ok": True, "state": "already_open", "status_file": str(heartbeat)}
        except (OSError, ValueError):
            pass
    try:
        freecad = find_freecad_python().parent/"FreeCAD.exe"
        if not freecad.exists():
            raise RuntimeError("FreeCAD GUI executable not found beside bundled Python")
        macro = project/"history"/"live_view.FCMacro"
        macro.parent.mkdir(parents=True, exist_ok=True)
        code = "import sys\n"+f"sys.path.insert(0, {str(HERE)!r})\n"+"import live_view\n"+f"live_view.start({str(project)!r})\n"
        macro.write_text(code, encoding="utf-8")
        # User explicitly wants a visible review window. No shell/console window.
        env = os.environ.copy()
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        env.setdefault("QT_OPENGL", "software")
        with (project/"history"/"live_view.log").open("a", encoding="utf-8") as log:
            subprocess.Popen([str(freecad), str(macro)], cwd=str(project), env=env,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                             close_fds=True)
        return {"ok": True, "state": "starting", "status_file": str(heartbeat)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "hint": "draft is saved; run live.py with the project path to retry"}


if __name__ == "__main__":
    import sys
    print(json.dumps(open_live(sys.argv[1]), indent=2))
