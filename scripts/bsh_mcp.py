"""Entry point: expose the BSH Research Center firm memory as a local MCP server (stdio)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import mcp_server  # noqa: E402

if __name__ == "__main__":
    mcp_server.serve()
