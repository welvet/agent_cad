"""Actual stdio MCP handshake, tool invocation, and inline image checks."""
import asyncio
import json
from pathlib import Path
import sys
import base64
import struct

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parents[1]


async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(HERE/"server.py")])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            assert {tool.name for tool in listing.tools} == {"execute_cad", "inspect_cad", "export_cad"}
            result = await session.call_tool("execute_cad", {"file_path": str(HERE/"examples"/"cube.cad.py"), "live": False})
            assert not result.isError, result
            images = [block for block in result.content if block.type == "image"]
            assert len(images) == 4, len(images)
            assert all(i.mimeType == "image/png" and len(i.data) > 100 for i in images)
            metadata = json.loads(result.content[0].text)
            assert metadata["valid"] and metadata["solid_count"] == 1
            assert "edges" not in metadata and metadata["edge_count"] > 0
            assert all(struct.unpack(">II", base64.b64decode(i.data)[16:24]) == (1024, 1024) for i in images)
            closeup = await session.call_tool("inspect_cad", {
                "file_path": metadata["freecad"], "view": "right",
                "region": [[0, 2, 2], [10, 8, 8]], "resolution": 512,
            })
            assert not closeup.isError, closeup
            close_metadata = json.loads(closeup.content[0].text)
            assert close_metadata["rebuilt"] is False
            assert len([b for b in closeup.content if b.type == "image"]) == 1
            print(json.dumps({"mcp": "passed", "tool_count": 3, "inline_images": len(images),
                              "inspection": "passed, one image without rebuilding",
                              "native_file": metadata["freecad"], "views": metadata["contact_sheet"],
                              "seconds": metadata["seconds"]}, indent=2))
            error = await session.call_tool("execute_cad", {"file_path": "relative.cad.py"})
            assert error.isError


if __name__ == "__main__":
    asyncio.run(main())
