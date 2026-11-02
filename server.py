"""Build and inspect CAD through stdio MCP."""
import asyncio
import base64
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent

from execute import execute_cad as build
from inspection import inspect_cad as inspect_saved
from exporting import export_cad as export_approved
from colored_export import export_colored_obj as export_obj_approved


mcp = FastMCP(
    "Agent CAD",
    instructions="Edit a .cad.py file using the documented helpers, then call execute_cad. "
    "Assign one final solid to root. Coordinates and dimensions use 0.1 mm increments; "
    "root must fit X/Y/Z 0..256 mm. Read " + str(Path(__file__).resolve().parent/"MODELING.md") + " for the helper API. "
    "Build saves a DRAFT native FCStd and four 1024px images in the project folder, and opens/refreshes FreeCAD. "
    "NEVER export during iteration. Only call export_cad or export_colored_obj after explicit USER approval. "
    "Colored OBJ uses project colors.py: PALETTE, color_at(x,y,z), optional SPLIT_PLANES. "
    "Use inspect_cad to zoom into saved CAD without rebuilding. "
    "Only execute trusted local model files; Python execution is unrestricted.",
)
lock = asyncio.Lock()


def response(result):
    # Keep complete geometry metadata on disk, rather than filling model context.
    summary = dict(result)
    if "edges" in summary:
        summary["edge_count"] = len(summary.pop("edges"))
        summary["edge_catalog"] = str(Path(result["run_directory"])/"result.json")
    content = [TextContent(type="text", text=json.dumps(summary, indent=2))]
    if result["ok"]:
        for name, path in result.get("views", {}).items():
            content.append(TextContent(type="text", text=f"{name.upper()} VIEW"))
            content.append(ImageContent(type="image", mimeType="image/png",
                                        data=base64.b64encode(Path(path).read_bytes()).decode("ascii")))
    return CallToolResult(isError=not result["ok"], content=content)


@mcp.tool()
async def execute_cad(file_path: str, project_dir: str | None = None, live: bool = True) -> CallToolResult:
    """Execute an absolute local .cad.py file. Return four images or a source-line error.

    Helpers are injected: box, cylinder, cone, sphere, tube, circle, rectangle,
    polygon, line, arc, spline, curve, polyline, wire, extrude, loft, revolve,
    sweep, pipe, array, radial_array. Set root to one solid. Solid methods:
    merge, subtract, intersect, move, rotate, mirror, scale, fillet, chamfer,
    hole (add/cut remain aliases). Profiles support offset().
    See MODELING.md for argument conventions.
    Every run is independent; edit the file to change the model and call again.
    Draft only: saves native model/images/history; never exports STEP. Project
    defaults to the source folder inside Documents/3d. live=True opens/updates
    the review window. Use live=False for automated/headless checks.
    """
    if not Path(file_path).is_absolute():
        return CallToolResult(isError=True, content=[TextContent(type="text", text="file_path must be absolute")])
    async with lock:
        result = await asyncio.to_thread(build, file_path, project_dir=project_dir, live=live)
    return response(result)


@mcp.tool()
async def inspect_cad(file_path: str, view: str = "isometric",
                      region: list[list[float]] | None = None,
                      resolution: int = 1024) -> CallToolResult:
    """Re-render saved CAD without rebuilding. Return fresh, fitted PNG images.

    file_path: absolute STEP/FCStd, successful result.json, or unchanged built
    model .cad.py. view: top/front/right/isometric/all. resolution: 256..2048.
    region: optional [[xmin,ymin,zmin],[xmax,ymax,zmax]] in 0.1 mm increments.
    A region zooms the viewport; it does not cut or section the solid. Keep the
    full solid for normal depth/occlusion. Omit region to fit the full model.
    """
    if not Path(file_path).is_absolute():
        return CallToolResult(isError=True, content=[TextContent(type="text", text="file_path must be absolute")])
    async with lock:
        result = await asyncio.to_thread(inspect_saved, file_path, view, region, resolution)
    return response(result)


@mcp.tool()
async def export_cad(project_dir: str, revision: str, approval: str) -> CallToolResult:
    """Export STEP ONLY AFTER explicit USER approval of the current draft.

    Do not infer approval from a build request, a valid model, or an agent's own
    judgment. revision must be the exact reviewed revision from execute_cad.
    approval must quote the user's explicit approval. Source/CAD changes
    invalidate approval. This records the approval and validates STEP round-trip.
    """
    async with lock:
        result = await asyncio.to_thread(export_approved, project_dir, revision, approval)
    return response(result)


@mcp.tool()
async def export_colored_obj(project_dir: str, revision: str, approval: str,
                             color_file: str | None = None) -> CallToolResult:
    """Export an approved saved draft as colored OBJ + MTL + ZIP, without rebuilding.

    Default color_file is <project>/colors.py. It defines PALETTE (named #RRGGBB
    or normalized RGB colors), color_at(x,y,z) returning a palette name, and
    optional SPLIT_PLANES={'x':[...],'y':[...],'z':[...]} in mm for crisp bands.
    Validates source/revision/native hash, snapshots the rules, tessellates CAD,
    assigns surface materials, and packages matching files for OrcaSlicer 2.5.
    Requires actual user approval of the current geometry and color scheme.
    No STL, no CAD edits, no printer settings. See COLORED_OBJ.md for examples.
    """
    async with lock:
        result = await asyncio.to_thread(export_obj_approved,project_dir,revision,approval,color_file)
    return response(result)


if __name__ == "__main__":
    mcp.run(transport="stdio")
