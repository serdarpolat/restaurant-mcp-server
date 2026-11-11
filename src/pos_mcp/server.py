"""MCP server exposing the restaurant POS to AI assistants.

Tools will be implemented on days 5-7.
"""

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("restaurant-pos")


@mcp.tool()
def ping() -> str:
    """Health check: returns 'pong' if the MCP server is running."""
    return "pong"


if __name__ == "__main__":
    mcp.run()
