# Colored OBJ export — agent guide

Use `export_colored_obj` to export surface colors from a saved native CAD draft.
It uses the same OBJ+MTL approach as the accepted coach export for OrcaSlicer 2.5.
No custom FreeCAD export script, geometry rebuild, STL intermediate, or slicer preset is needed.

## Workflow

1. Build and review geometry with `execute_cad` as usual.
2. Put a self-contained `colors.py` beside `model.cad.py`.
3. Get explicit user approval for the current geometry and color scheme.
4. Call `export_colored_obj` with the current revision and approval quote.
5. Deliver the ZIP. Keep its OBJ and MTL together after extraction.

## colors.py

```python
PALETTE = {"Blue": "#085BB5", "Silver": "#C3C8CD", "Red": "#D32632"}
SPLIT_PLANES = {"z": [3, 7]}  # optional sharp paint boundaries, in mm

def color_at(x, y, z):
    if z < 3:
        return "Blue"
    if z < 7:
        return "Silver"
    return "Red"
```

`PALETTE` maps material names to `#RRGGBB` strings or normalized RGB tuples
in 0..1. Names start with a letter and contain only letters/digits/underscores.
`color_at(x,y,z)` receives a triangle's surface centroid in global millimeters.
Return a palette name. Use normal Python conditions for bands, doors, windows,
or other regions. The function must be deterministic and have no side effects.
A single-color palette may omit the function.

Optional `SPLIT_PLANES` maps `x`, `y`, `z` to plane positions in 0.1 mm steps.
For example, `{"x":[25,39],"z":[10,28]}` aligns a rectangular door-color region.
Planes subdivide mesh triangles, not CAD geometry. Declare useful boundaries,
not a dense voxel grid (maximum 128 planes). Arbitrary curved color borders are
sampled at mesh resolution. Without a split plane, a broad triangle can straddle
a color boundary and receives the material at its centroid.

The file is copied into the export directory before execution: keep it independent
of neighboring modules, textures, or relative data files. It is trusted local
Python, with the same execution trust as a model script. See [examples/colors.py](examples/colors.py).

## MCP call

```json
{
  "project_dir": "C:/CADProjects/my_project",
  "revision": "<exact reviewed revision>",
  "approval": "<quote the user's explicit approval>",
  "color_file": "colors.py"
}
```

`color_file` is optional; default `<project>/colors.py`. Absolute paths inside
the project also work. Approval must cover the actual current colors and geometry.
The agent must obtain real approval and never invent it or reuse an old quote
for a changed design. The tool checks geometry source/revision/native CAD hashes,
then snapshots and hashes the color rules for the export receipt.

CLI fallback uses the same backend:

```powershell
& '<tool>\.venv\Scripts\python.exe' '<tool>\colored_export.py' '<project>' `
  --revision '<reviewed revision>' --approval '<user approval quote>'
```

## What it does

1. Opens the saved native CAD, without executing the geometry source again.
2. Tessellates the solid at 0.02 mm deflection into triangles in memory.
3. Subdivides triangles at declared paint planes for crisp band/door boundaries.
4. Calls `color_at` on triangle centers and assigns named materials.
5. Writes `model.obj` (geometry and material references) and `model.mtl` (RGB colors).
6. Records dimensions, triangle/material counts and mesh-edge warnings, then
   packages matching OBJ/MTL files and import instructions into `colored_obj.zip`.

Outputs stay under:

```text
<project>/exports/<revision>/obj_<color-hash>/
  model.obj
  model.mtl
  colored_obj.zip
  colors.py             # exact rule snapshot
  export_info.json      # palette, dimensions, mesh stats and warnings
  approval.json         # user quote, CAD revision/hash, color hash
  README.txt
  job.json / result.json / worker.log
```

Existing exports are preserved. The same revision/color combination cannot be
overwritten. New color rules produce a different hash/folder. Working CAD,
the geometry script, standard previews, and live review window are unchanged.

## OrcaSlicer 2.5

Extract the ZIP. Import `model.obj` with `model.mtl` beside it. In Import Model,
choose the color count and map the colors to your project filaments. Printer,
nozzle, process, and filament profiles are not embedded or changed.

These are surface colors for Orca's color-painting importer, not separate material
volumes, transparent glass, or textures. This first automation does not paint the
live FreeCAD BRep or ordinary draft preview images: review colors in the OBJ import.

CAD validity does not guarantee a clean printable tessellation. The result reports
`source_mesh_edge_anomalies` and `mesh_edge_anomalies`; it never silently repairs
or changes the CAD shape. Tangent contacts may need slicer repair. No STEP or STL.
