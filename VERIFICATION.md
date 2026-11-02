# Verification — 2026-11-02

- 12 real FreeCAD geometry tests pass.
- 3 framing/render tests pass.
- 6 execution/project/approval tests pass, including last-good preservation,
  no STEP during draft builds, missing/stale approval rejection, changed-source
  rejection, and an isolated synthetic-fixture STEP round-trip.
- Actual stdio MCP handshake/build/inspection passes with all three tools listed;
  draft build returns four 1024px images and native CAD, not STEP.
- Live FreeCAD smoke test refreshed a saved draft while keeping the camera;
  `tests/live_smoke/live_status.json` reported `camera_preserved: true` and the
  current revision `20261102T210025_b67535e6`. Its native viewport also rendered.
- Actual double-decker v2 rebuilt as a DRAFT in its existing task folder:
  revision `20261102T204925_b5d97c89`, 214 x 30.2 x 39 mm, one valid solid.
  Working native CAD and project previews were saved; no new STEP was produced.
  The coach was verified visibly open in the native FreeCAD review window.
- Setup PowerShell syntax checked. Existing installed dependencies used for
  runtime checks; a fresh internet-dependent installation was not performed.
- Source ZIP integrity checked; excludes .venv, user CAD, STL, STEP, and history.

Approval is a caller policy plus revision/hash checks, not independent human
authentication. The agent must wait for real user approval and quote it honestly.
GUI geometry edits do not round-trip back into the source script.

## Colored OBJ automation (v0.3.0)

- Three added tests cover palette validation, invalid material callbacks, sharp
  color boundaries, closed mesh topology, unchanged cube area/volume, approval
  rejection, complete OBJ/MTL/ZIP contents, and unchanged native CAD bytes.
- Actual MCP test lists four tools and successfully exports the synthetic cube
  with three named materials, with `rebuilt: false`.
- The current project's separate color rules also ran through the generic mesh
  painter without rebuilding or exporting its native CAD. Material grouping and
  source-vs-colored edge counts were checked.
- The 3MF/Orca painting importer is not implemented by this tool. It produces
  OBJ+MTL surface colors for import into the user's slicer; it does not choose
  hardware, printer profiles, material volumes, or start a print.
