"""FreeCAD worker for generic colored OBJ export. No STL and no geometry rebuild."""
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
import zipfile

import FreeCAD as App
from obj_colors import load_colors,colored_mesh,write_obj


def main(job_path):
    job=json.loads(Path(job_path).read_text(encoding="utf-8"))
    output=Path(job["output"])
    doc=None
    started=time.monotonic()
    try:
        cad,colors=Path(job["cad_file"]),Path(job["color_file"])
        if not job.get("approval"):
            raise ValueError("explicit user approval required")
        if hashlib.sha256(cad.read_bytes()).hexdigest()!=job["cad_sha256"]:
            raise ValueError("native CAD differs from approved revision")
        if hashlib.sha256(colors.read_bytes()).hexdigest()!=job["color_sha256"]:
            raise ValueError("color rules differ from approved snapshot")
        palette,color_at,planes=load_colors(colors)
        doc=App.openDocument(str(cad))
        shape=doc.getObject("Root").Shape
        if not shape.isValid() or len(shape.Solids)!=1:
            raise ValueError("saved Root must be one valid connected solid")
        vertices,groups,stats=colored_mesh(shape,palette,color_at,planes)
        obj,mtl=write_obj(output,vertices,groups,palette)
        warnings=[]
        if stats["source_mesh_edge_anomalies"]:
            warnings.append(f"Source CAD tessellation has {stats['source_mesh_edge_anomalies']} edge anomalies; slicer repair may be needed.")
        if stats["mesh_edge_anomalies"]>stats["source_mesh_edge_anomalies"]:
            warnings.append("Color boundary splitting increased edge anomalies; inspect the mesh before printing.")
        result={"ok":True,"format":"colored_obj","revision":job["revision"],"rebuilt":False,
                "obj":str(obj),"mtl":str(mtl),"color_sha256":job["color_sha256"],
                "units":"mm","palette":{k:list(v) for k,v in palette.items()},
                "warnings":warnings,**stats,"seconds":round(time.monotonic()-started,2)}
        (output/"export_info.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        (output/"README.txt").write_text(
            "Keep model.obj and model.mtl together. Import model.obj into OrcaSlicer 2.5.\n"
            f"Use {len(palette)} colors in Import Model and map them to your filaments. Units: mm; Z up.\n"
            "These are surface colors, not separate material volumes. No printer/process presets are included.\n",
            encoding="utf-8")
        archive=output/"colored_obj.zip"
        with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as file:
            for path in (obj,mtl,output/"README.txt",output/"export_info.json"):
                file.write(path,path.name)
        result["zip"]=str(archive)
    except Exception as exc:
        result={"ok":False,"phase":"colored_obj","error":str(exc),"error_type":type(exc).__name__,
                "traceback":traceback.format_exc()}
    finally:
        if doc is not None:
            App.closeDocument(doc.Name)
    (output/"result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__=="__main__":
    sys.exit(main(sys.argv[1]))
