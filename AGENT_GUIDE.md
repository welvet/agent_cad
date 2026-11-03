# Agent CAD — agent operating guide

**Build drafts, review with the user, export only after explicit approval.**
The tool manages FreeCAD boilerplate, geometry checks, native saving, previews,
and live review. Read [MODELING.md](MODELING.md) for the full modeling API.

## Project structure

Create or reuse a task folder under `C:\Users\you\Documents\3d`. Never put
models, scripts, or images directly at the workspace root. One active design
per project; keep source in `model.cad.py`.

```text
<project>/
  model.cad.py           # authoritative editable source
  model.FCStd            # latest successful working CAD
  project.json           # current revision and source/CAD hashes
  previews/              # latest full-size views and requested close-ups
  history/<revision>/    # immutable source, CAD, images, metadata, logs
  history/inspections/   # prior close-up renders
  exports/<revision>/    # STEP and approval receipt, after user approval
  last_error.json        # failure details; previous good draft is preserved
  live_status.json       # viewer heartbeat, displayed revision, errors/pauses
```

The source folder is the default project. Supply `project_dir` if it differs.
A differently named source is also copied to canonical `model.cad.py`.

## Modeling

```python
root = box(10, 10, 10).fillet(0.5)
root = root.hole(2, 5, at=(5, 5, 10))
```

Helpers are injected. Do not write FreeCAD imports, render code, or exports.
Final `root` must be one valid connected solid. Input coordinates/dimensions
use 0.1 mm steps; root fits X/Y/Z 0..256 mm. Temporary cutters can extend beyond
the workspace. Prefer rounded planar profiles over filleting many thin cutters.

## Parts for separate color assignment

When the user wants multiple colors, plan independent physical parts before
modeling. Split at useful manufacturing boundaries (body, roof, windows, trim),
not surface paint regions. Each part needs actual solid geometry and thickness.
Do not merge parts that must remain separately selectable for later coloring.

The current tool accepts one connected solid per build, not an assembly root.
Use a separate subproject for each part:

```text
<project>/
  PARTS.md                  # part names, intended colors, shared placement, fits
  parts/body/model.cad.py
  parts/roof/model.cad.py
  parts/trim/model.cad.py
```

Each subproject gets its own native CAD, previews, history, revision, and STEP.
Use a shared coordinate frame within the positive workspace so exported parts
retain their relative placement. Avoid overlapping volumes; document any intended
fit clearance and check mating dimensions. If a color group contains disconnected
pieces, give each connected piece its own part subproject.

Review every part and their fit with the user. Obtain approval covering the exact
current revisions, then call export_cad separately for each approved part. Deliver
all STEP paths and PARTS.md. The downstream application assigns colors/materials
to the individual parts; STEP here carries geometry, not a filament assignment.
The tool does not yet generate a combined assembly preview or assembly STEP.
Existing single-solid projects remain valid; splitting them requires a new draft
and review, not reusing approval from the fused model.

## Draft build: execute_cad

```json
{
  "file_path": "C:/Users/you/Documents/3d/my_project/model.cad.py",
  "project_dir": "C:/Users/you/Documents/3d/my_project",
  "live": true
}
```

Success validates geometry, saves native working CAD and four independently
fitted 1024px PNGs, retains immutable history, opens/updates FreeCAD, and returns
`status: draft`, `exported: false`, and the exact `revision`. **No STEP or STL.**
Use `live=false` for automated/headless checks. Failed builds save diagnostics
and preserve the previous good working CAD/previews. The manifest commits last,
so the viewer sees completed revisions only. No automatic history deletion.

## Close-ups: inspect_cad

```json
{
  "file_path": "C:/Users/you/Documents/3d/my_project/model.FCStd",
  "view": "right",
  "region": [[190,10,8],[220,26,33]],
  "resolution": 1024
}
```

Opens saved CAD without running source again (`rebuilt: false`). Accepts native
FCStd, successful result.json, unchanged built .cad.py, or legacy/user STEP.
Views: top/front/right/isometric/all. Resolution: 256..2048. Optional region is
min/max XYZ in 0.1 mm steps: viewport zoom, not a section cut. Hidden geometry
stays hidden. With a vehicle along X, FRONT is its side and RIGHT its end.

Use separate full-size images and detail views, not just the thumbnail sheet.
Inspection saves `previews/inspect_<view>.png` and historical renders. Large edge
catalogs stay on disk; read the linked `edge_catalog` only when required.

## Live review with the user

FreeCAD remains visibly open for rotating, zooming, selecting, measuring, and
feedback. Updates restore camera position/orientation/scale. The live document
is saved separately as `history/live_review.FCStd`; the worker owns `model.FCStd`.
The GUI polls the committed manifest about every 0.75 seconds.

The Python source is authoritative. GUI geometry changes are not synchronized
back into it. If Root's shape changes in the GUI, refresh pauses with
`paused_user_geometry_changed` rather than replacing it. Preserve those edits
and ask how to reconcile them. Camera changes do not pause updates. This is not
bidirectional parametric editing or a native PartDesign feature-tree generator.

Closing the review document stops the watcher. To reopen a saved project:

```powershell
& '<tool>\.venv\Scripts\python.exe' '<tool>\live.py' '<project>'
```

`starting` only means launch was attempted. Verify `live_status.json` reports
`watching`/`updated` and the current revision, or inspect the window. Surface
viewer errors to the user; the saved draft remains available.

## Approval and export: export_cad

Show the current draft and explain material limitations. Wait for explicit
USER approval. A build request, agent judgment, or validation success is not it.

```json
{
  "project_dir": "C:/Users/you/Documents/3d/my_project",
  "revision": "<exact reviewed revision>",
  "approval": "<quote the user's explicit approval>"
}
```

Rejects empty approval, old revision, changed source, changed native snapshot,
or overwriting an existing export. Exports STEP and reimports it to check one
valid solid and volume agreement. Saves an approval receipt with the revision,
CAD hash, and supplied quote. The agent must obtain genuine approval: the tool
cannot authenticate the human behind a string. Never invent/reuse approval for
a changed design. Deliver a STEP link AND full absolute Windows path in a code
block. Preserve exports. Generate STL only if explicitly requested.

## Setup and recovery

Run `setup.ps1` to create the local .venv, install the pinned MCP SDK, verify
FreeCAD, and generate `mcp-config.local.json`. Add that config to your MCP client;
setup does not change global agent settings.

Server command: `<tool>/.venv/Scripts/python.exe <tool>/server.py`.
CLI draft: `python execute.py <source> [--project-dir <project>] [--no-live]`.

Windows/FreeCAD 1.1 tested. Bundled Python needs FreeCAD, Part, NumPy, and Pillow.
Override executable via `AGENT_CAD_FREECAD_PYTHON`. If moving the package outside
this layout, set `AGENT_CAD_WORKSPACE` to the project workspace. Timeout: 120s.
Read failed revision logs. Do not bypass backend validation for ordinary tasks.
Model scripts are trusted local Python, not sandboxed uploads. No hidden STL
exports or cloud services.
