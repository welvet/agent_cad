"""Approval-bound colored OBJ/MTL export from a saved draft, without rebuilding."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from execute import find_freecad_python, _run_worker
from exporting import reviewed_draft
from project import atomic_json


def export_colored_obj(project_dir, revision, approval, color_file=None, timeout=120):
    try:
        project,manifest,cad,cad_hash = reviewed_draft(project_dir,revision,approval)
        colors = Path(color_file) if color_file else project/"colors.py"
        if not colors.is_absolute():
            colors = project/colors
        colors = colors.resolve()
        if not colors.is_relative_to(project) or colors.suffix != ".py" or not colors.is_file():
            raise ValueError("color_file must be an existing Python file inside the project; default colors.py")
        if colors == Path(manifest["source"]).resolve():
            raise ValueError("put only palette/paint rules in a separate colors.py, not in the geometry source")
        code = colors.read_bytes()
        digest = hashlib.sha256(code).hexdigest()
        output = project/"exports"/revision/("obj_"+digest[:12])
        if (output/"model.obj").exists():
            raise ValueError("this revision/color combination is already exported; preserve the existing files")
        output.mkdir(parents=True,exist_ok=True)
        snapshot = output/"colors.py"
        snapshot.write_bytes(code)
        job = {"cad_file":str(cad), "cad_sha256":cad_hash, "color_file":str(snapshot),
               "color_sha256":digest, "revision":revision, "approval":approval.strip(),
               "output":str(output)}
        job_path = output/"job.json"
        atomic_json(job_path,job)
        result = _run_worker(find_freecad_python(),"obj_worker.py",job_path,output,timeout)
        if result["ok"]:
            atomic_json(output/"approval.json",{"revision":revision,"user_approval":approval.strip(),
                        "cad_sha256":cad_hash,"color_sha256":digest,"obj":result["obj"]})
        return result
    except Exception as exc:
        return {"ok":False,"phase":"approval","error":str(exc),"error_type":type(exc).__name__}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description="Export an approved draft as colored OBJ + MTL")
    parser.add_argument("project_dir")
    parser.add_argument("--revision",required=True)
    parser.add_argument("--approval",required=True)
    parser.add_argument("--color-file")
    args=parser.parse_args()
    result=export_colored_obj(args.project_dir,args.revision,args.approval,args.color_file)
    print(json.dumps(result,indent=2))
    sys.exit(0 if result["ok"] else 1)
