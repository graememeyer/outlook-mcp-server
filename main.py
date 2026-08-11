import sys

from server import mcp
from auth.tools import *
from mail.tools import *
from config import settings

if __name__ == "__main__":
    transport = settings.MCP_TRANSPORT.lower()

    if transport in ("http", "streamable-http"):
        # Hosted/remote deployment (e.g. behind an authentik-fronted reverse
        # proxy). Bind to MCP_HOST/MCP_PORT so the proxy can reach it.
        print(
            f"Starting Outlook MCP Server (HTTP) on "
            f"{settings.MCP_HOST}:{settings.MCP_PORT}{settings.MCP_PATH} ...",
            file=sys.stderr,
        )
        mcp.run(
            transport="http",
            host=settings.MCP_HOST,
            port=settings.MCP_PORT,
            path=settings.MCP_PATH,
        )
    else:
        # Local use: stdio transport spawned by the MCP client. Startup logging
        # must go to stderr so it can't corrupt the JSON-RPC stream on stdout.
        print("Starting Outlook MCP Server (stdio)...", file=sys.stderr)
        mcp.run()
