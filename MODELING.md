# Agent CAD: model file guide

Edit one `.cad.py` file, then call `execute_cad(file_path)` with its absolute path.
The tool loads the file, builds one solid, validates it, saves native draft FCStd,
and returns four PNG images: top, front, right, isometric. It does not export STEP
until user approval through the separate export tool. Read AGENT_GUIDE.md for
project storage and live-review workflow. No imports or FreeCAD
boilerplate are needed in model files. The helpers below are injected.

## Core vocabulary

| Task | Tools |
| --- | --- |
| Solids | `box`, `cylinder`, `cone`, `sphere`, `tube` |
| Flat profiles | `circle`, `rectangle`, `polygon`, closed `spline` or `wire` |
| Paths | `line`, `arc`, `polyline`, `spline` |
| Build volume | `extrude`, `revolve`, `loft`, `sweep`, `pipe` |
| Booleans | `.merge`, `.subtract`, `.intersect` |
| Repeat / position | `array`, `radial_array`, `.move`, `.rotate`, `.mirror`, `.scale` |
| Finish / adjust | `.fillet`, `.chamfer`, `.hole`, profile `.offset` |

A **spline** draws a smooth path or outline through points. A **loft** connects
multiple closed outlines. A **sweep** carries an outline along a path; **pipe**
does this with an automatically positioned circular outline. No sheet or patch
operations are exposed. Profiles and paths are construction tools only.

## Rules

- Assign the final solid to **`root`**. Temporary solids are cutting/adding tools.
- Every solid operation must result in one connected, valid solid. Disconnected
  assemblies are outside v1. Tools are not exported.
- Root must fit **X = 0..256, Y = 0..256, Z = 0..256 mm**. Temporary tools may
  extend outside this workspace, e.g. to cut completely through a part.
- Dimensions, coordinates, and translations must be multiples of **0.1 mm**.
  Angles use multiples of 0.1 degree. Finer values are rejected, not rounded.
- This is input resolution, not geometric quantization: circles remain circles;
  computed radii, intersections, and kernel tolerances retain CAD precision.
- Coordinates are global, right-handed XYZ. Z is up. All lengths are millimeters.
- Helpers return new objects. Write `root = root.fillet(0.5)`, not just
  `root.fillet(0.5)`.
- The source file is the editable design. Each execution rebuilds independently.

## Minimal model

```python
root = box(10, 10, 10)
root = root.fillet(0.5)
root = root.hole(diameter=2, depth=5, at=(5, 5, 10))
```

The box occupies (0,0,0)..(10,10,10). All twelve outside edges are rounded
before cutting a flat-bottom hole downward from its top center.

## Primitives

```python
box(x, y, z, at=(0, 0, 0))
cylinder(diameter, height, at=(0, 0, 0), axis="Z")
cone(bottom_diameter, top_diameter, height, at=(0, 0, 0), axis="Z")
sphere(diameter, at=(0, 0, 0))
tube(outer_diameter, wall, height, at=(0, 0, 0), axis="Z")
```

- Box `at` is its minimum XYZ corner; it extends positively along each axis.
- Cylinder/cone/tube `at` is the center of the starting end, and height runs
  along `axis`. Diameters are full diameters, not radii. Cone top diameter can
  be zero. Tube `wall` is radial wall thickness.
- Sphere `at` is its center.
- Axis values: `"X"`, `"Y"`, `"Z"`, `"-X"`, `"-Y"`, `"-Z"`.

## Solid operations

```python
root = root.add(tool, another_tool)       # union; tools must connect to root
root = root.cut(tool, another_tool)       # subtract; each must remove material
root = root.merge(tool, another_tool)     # same as add; also accepts arrays
root = root.subtract(tool, another_tool)  # same as cut; also accepts arrays
root = root.intersect(tool)              # keep shared volume
root = root.move((dx, dy, dz))
root = root.rotate(angle, axis="Z", at=(0, 0, 0))
root = root.mirror(plane="YZ", at=(0, 0, 0))
root = root.scale(factor, at=(0, 0, 0))   # uniform scale; positive factor
root = root.fillet(radius, edges="all")
root = root.chamfer(distance, edges="all")
root = root.hole(diameter, depth, at=(x, y, z), axis="-Z")
```

Hole `at` is its mouth center. Depth is positive and runs along `axis`;
the default cuts downward. For a through hole, choose a depth that extends
past the opposite surface. For rotated solids all helpers still use global axes.

Fillet and chamfer selections:

- `"all"`: every edge, including hole rims if the holes already exist.
- `"vertical"`: straight edges parallel to global Z.
- `"top"` / `"bottom"`: edges entirely at the solid's maximum/minimum global Z.
- `["E1", "E4"]`: individual edge IDs from the most recent execution result.

Edge IDs belong to the shape **at that operation**. Use returned IDs when adding
a final operation after an unchanged prefix. They are not stable references
across topology changes. Put external fillets before holes to leave hole rims sharp.

All transformations return copies and preserve the source object. For example,
`other = tool.move((10, 0, 0))` duplicates it at a translated position. Mirror
returns only the mirrored copy: use `root.merge(root.mirror(...))` for symmetry.
Mirror planes are global XY/XZ/YZ planes passing through `at`. Scale is uniform
about `at`; factors use 0.1 increments. Derived coordinates retain CAD precision.

## Arrays and repeated cuts

```python
array(tool, count=4, step=(10, 0, 0))
array(tool, count=(3, 2, 1), step=(10, 12, 0))
radial_array(tool, count=6, at=(30, 30, 0), axis="Z", angle=360)
```

`count` always includes the original position. An integer count creates a linear
array with a full XYZ step vector. `(nx,ny,nz)` creates a rectangular grid, with
per-axis spacing. Each repeating axis needs a nonzero spacing. Arrays return
lists of tools, not a disconnected solid. Pass them directly into merge/subtract:

```python
root = box(40, 30, 5)
drill = cylinder(3, 7, at=(5, 5, 6), axis="-Z")
holes = array(drill, count=(4, 3, 1), step=(10, 10, 0))
root = root.subtract(holes)
```

For radial arrays, `at` and `axis` define the rotation axis. Copies rotate in
the positive right-hand direction. A full 360-degree pattern has no duplicate
at the endpoint; a partial angle includes both endpoints. Seven evenly spaced
copies are supported: derived angles and coordinates are not snapped to 0.1.
An array has at most 1000 copies. The final merged/subtracted result must be one
connected solid. Nested lists of tools are accepted by merge/subtract.

## Profiles, extrusions, and lofts

A profile is a closed, planar outline, not a solid. Circle and rectangle are
profiles; cylinder and box are solids.

```python
circle(diameter, at=(0, 0, 0), plane="XY")
rectangle(width, height, at=(0, 0, 0), plane="XY")
polygon([(u, v), ...], at=(0, 0, 0), plane="XY")
profile.offset(distance, corners="round")

extrude(profile, height, axis="Z")
loft([profile1, profile2, ...], ruled=False)
revolve(profile, angle=360, axis="Z", at=(0, 0, 0))
```

`plane` is `"XY"`, `"XZ"`, or `"YZ"`. Its local (u,v) coordinates map to
(x,y), (x,z), or (y,z), then `at` is added. A circle is centered at `at`;
a rectangle starts at `at`. Polygon points are 2D local coordinates.
Extrusion axis must leave the profile plane (XY->Z, XZ->Y, YZ->X).

A tapered or dress-like form needs only two or more circle profiles:

```python
root = loft([
    circle(30, at=(20, 20, 0)),
    circle(10, at=(20, 20, 35)),
])
```

`ruled=True` requests straight interpolation between consecutive sections;
otherwise FreeCAD creates a smooth loft. Profile order defines the progression.
Lofting compatible closed outlines creates a capped solid, not a hollow shell.
Make a hollow loft by subtracting a second loft that opens through its end.

Profile offset expands an outline for positive distances or shrinks it for
negative distances. `corners="round"` rounds convex joins; `"sharp"` intersects
adjacent segments. It must produce one closed outline. This is a planar outline
operation, not a solid-face offset. Extrude the resulting profile to get volume.

## Lines, arcs, curves, and sweeps

```python
line(start, end)                       # two global XYZ points
arc(start, through, end)               # three global XYZ points
polyline([point1, point2, ...], closed=False)  # connected straight segments
spline([point1, point2, ...], closed=False)    # interpolated B-spline
wire(segment1, segment2, ..., closed=False)
sweep(profile, path)
pipe(diameter, path, wall=None)
```

Open results are paths. `closed=True` creates a planar closed profile that can
be extruded, lofted, revolved, or swept. Wire segments must connect in order.
An open curve needs at least three points. Curves interpolate all supplied points.
`curve(...)` remains an alias for `spline(...)`. Polyline needs two points, or
three for a closed profile. All line/arc/spline/polyline points are global XYZ.
Sweep profiles should be positioned at the path start and perpendicular to its
initial direction. v1 uses the kernel's standard non-Frenet sweep orientation.

Pipe automatically places a circular profile at the start of the path and
aligns it perpendicular to the initial tangent, including non-axis-aligned paths.
With no `wall`, the result is a solid round rod. A positive radial `wall` makes
a hollow tube with open ends. Wall thickness must be less than half the diameter.
Sharp corners or bends tighter than the pipe radius can fail; use smooth arcs or
splines instead. Example:

```python
route = spline([(10, 10, 0), (10, 10, 15), (20, 10, 25)])
root = pipe(6, route, wall=1)
```

Example: extrude an outline with a semicircular end:

```python
outline = wire(
    line((0, 0, 0), (10, 0, 0)),
    arc((10, 0, 0), (15, 5, 0), (10, 10, 0)),
    line((10, 10, 0), (0, 10, 0)),
    line((0, 10, 0), (0, 0, 0)),
    closed=True,
)
root = extrude(outline, 5)
```

## Feedback and iteration

Success returns four separate 1024 x 1024 inline MCP images, dimensions/bounds
in mm, volume in mm3, edge count, and absolute native FCStd/PNG paths. The full
edge catalog remains in the saved result JSON linked as `edge_catalog`, rather
than filling the tool response. `views.png` is a 1024 x 1024 thumbnail sheet;
use the separate full-resolution images to inspect detail.

Each build has a new directory under `<project>/history/<revision>/`.
It contains a source snapshot, result JSON, logs, and successful outputs.
Failed executions return `ok: false`, phase, error, and the model source line
when available. They never return old images or old STEP paths as a success.
An execution has a 120-second timeout. Edit the source and execute again.

Preview conventions: top looks down from +Z (X right, Y up); front looks from
-Y (X right, Z up); right looks from +X (Y right, Z up); isometric looks from
(+X,-Y,+Z). Each view fits its own projected geometry independently, using about
90% of the available width or height. Views therefore have different mm/pixel
scales. `framing` reports each scale and projected size. A coach built along X
has its side in FRONT and its end in RIGHT; these labels refer to world axes.
These are shaded software renders from CAD tessellation with a depth buffer,
not screenshots of a GUI. No STL is written or required.

## Inspect saved CAD without rebuilding

```python
inspect_cad(
    file_path="C:/absolute/path/model.step",
    view="right",
    region=[[190, 10, 8], [220, 26, 33]],
    resolution=1024,
)
```

This is a separate MCP tool, not a helper inside the model file. It opens saved
CAD and renders fresh pixels at the requested camera/zoom. It does not execute
the model script, change the solid, regenerate STEP, or upscale an old PNG.

- `file_path`: absolute STEP/STP or exported FCStd (with Root object). A successful
  `result.json` also works. For `.cad.py`, inspection finds the newest successful
  build matching the current source hash; edited/unbuilt source is rejected.
- `view`: `top`, `front`, `right`, `isometric`, or `all`. Default: `isometric`.
- `region`: optional min/max XYZ corners in 0.1 mm increments. This fits the
  projected box in the viewport; it does not section the solid or reveal hidden
  geometry. Omit it to fit the full object independently in each requested view.
- `resolution`: integer 256..2048, default 1024 pixels per square image.

Inspection returns `rebuilt: false`, the saved CAD hash, images, and framing
metadata. Project inspections go in `history/inspections/` and current images
in `previews/`. Legacy external CAD uses `.cad-inspections` beside the CAD file.

## Scope of v1

No mesh-reference overlays, automatic feature fitting, interactive pixel selection,
assemblies, or sketch constraint solver interface yet. The exported FCStd contains
one final Root shape and a copy of its source, not an editable PartDesign feature
tree. To change the design, edit the `.cad.py` file and execute again. This keeps
the first implementation small; native feature history can be a later backend.

Model scripts are ordinary trusted Python with unrestricted execution. This is
a local development tool, not a sandbox for untrusted uploaded scripts.
