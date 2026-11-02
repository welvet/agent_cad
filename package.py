"""Build a clean source package; exclude user models, history, and environments."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
VERSION = "0.2.0"


def main():
    files = sorted({*HERE.glob("*.py"), *HERE.glob("*.md"), HERE/"requirements.txt", HERE/"setup.ps1",
                    *(HERE/"examples"/f"{name}.cad.py" for name in ("cube", "loft", "arrays_pipe")),
                    *HERE.glob("tests/test_*.py"), HERE/"tests/check_mcp.py"})
    output = HERE/"dist"/f"agent-cad-{VERSION}.zip"
    output.parent.mkdir(exist_ok=True)
    manifest = {"version": VERSION, "files": {str(p.relative_to(HERE)).replace("\\", "/"):
                hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, "agent_cad/"+path.relative_to(HERE).as_posix())
        archive.writestr("agent_cad/PACKAGE_MANIFEST.json", json.dumps(manifest, indent=2))
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert not any(name.lower().endswith((".step", ".stl", ".fcstd")) for name in archive.namelist())
    print(json.dumps({"package": str(output), "version": VERSION, "files": len(files),
                      "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__":
    main()
