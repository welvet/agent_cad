# Agent CAD MCP

**Read [AGENT_GUIDE.md](AGENT_GUIDE.md) first for live review, project storage,
and approval policy.**

`execute_cad(file_path, project_dir?, live=True)` builds a DRAFT, saves native
CAD/previews/history in the project folder, and opens/refreshes FreeCAD. No STEP.
`inspect_cad(file_path, view, region, resolution)` renders saved CAD with optional
close-ups, without rebuilding or exporting the geometry again.
`export_cad(project_dir, revision, approval)` exports STEP only after explicit
user approval of the current unchanged revision, with an approval receipt.
`export_colored_obj(project_dir, revision, approval, color_file?)` writes colored
OBJ+MTL+ZIP for OrcaSlicer 2.5 using project `colors.py`, without rebuilding CAD.
Read **[COLORED_OBJ.md](COLORED_OBJ.md)** for instructions and how it works.

Read **[MODELING.md](MODELING.md)** for the model-writing API.

The core tool selection follows the common solid operations in
[Plasticity's command list](https://github.com/nkallen/plasticity-document/blob/main/pages/all-commands/solid-commands.en.mdx):
booleans, extrude, revolve, loft, pipe, sweep, fillet, and chamfer. Repetition
uses linear/grid and radial arrays. Mirror, scale, and planar profile offset
complete the basic positioning and outline tools; no surface patches are exposed.

Examples: `examples/cube.cad.py`, `examples/loft.cad.py`, and
`examples/arrays_pipe.cad.py` (curved hollow pipe merged into a plate, radial holes).

## Installed setup

This project uses FreeCAD 1.1's bundled Python for the geometry worker.
The MCP server has its own `.venv` with the official MCP Python SDK.
FreeCAD, NumPy, and Pillow must be available in the worker interpreter.
The live review window is optional (`live=false` or CLI `--no-live` for headless).
No STL files are generated. Run `setup.ps1` for a copied/extracted installation;
it writes `mcp-config.local.json` without changing global agent settings.

From this directory, test the same execution path without MCP:

```powershell
.\.venv\Scripts\python.exe execute.py examples\cube.cad.py
```

To recreate the server environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the stdio MCP server:

```powershell
.\.venv\Scripts\python.exe server.py
```

It waits for MCP messages on stdin; use an MCP client to call it.
Use [mcp-config.example.json](mcp-config.example.json) as a template, or run
`setup.ps1` to generate a config using your local installation paths.
Other clients need the same executable and argument in their own config format.
The server exposes these four tools. Its config is provided, not automatically
installed in any agent application's global settings.

FreeCAD is discovered in standard Windows installation folders. To override:

```powershell
$env:AGENT_CAD_FREECAD_PYTHON = 'C:\Program Files\FreeCAD 1.1\bin\python.exe'
```

## Implementation

- `cad_tools.py`: high-level primitives, profiles, and immutable solid operations.
- `execute.py`: source snapshots, runtime discovery, timeout, worker subprocess.
- `worker.py`: executes the model, validates and saves native draft CAD.
- `project.py`: project storage, immutable revisions, last-good working files.
- `live.py` / `live_view.py`: visible FreeCAD review and camera-preserving refresh.
- `exporting.py` / `export_worker.py`: approval-bound STEP and round-trip checks.
- `colored_export.py` / `obj_worker.py` / `obj_colors.py`: colored OBJ materials,
  paint-boundary tessellation, mesh statistics, and ZIP packaging.
- `render.py`: four deterministic orthographic shaded views; no GUI or STL.
- `inspection.py` / `inspect_worker.py`: camera and region views of saved CAD.
- `server.py`: build/inspection tools returning concise JSON and full-size PNGs.

Coordinates and sizes are in 0.1 mm increments. Root is one connected solid
inside a 256 x 256 x 256 mm positive-coordinate workspace. Geometry retains
full kernel precision. The Python source is the editable model; v1 does not
generate a native FreeCAD PartDesign history tree.

## Checks

```powershell
& 'C:\Program Files\FreeCAD 1.1\bin\python.exe' tests\test_geometry.py
& 'C:\Program Files\FreeCAD 1.1\bin\python.exe' tests\test_render.py
& 'C:\Program Files\FreeCAD 1.1\bin\python.exe' tests\test_obj_colors.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_execution.py'
.\.venv\Scripts\python.exe tests\check_mcp.py
```
