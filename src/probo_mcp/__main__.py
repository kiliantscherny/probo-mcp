"""Command-line entry point: ``probo-mcp`` / ``python -m probo_mcp``."""

import argparse
import logging
import os
import sys

from . import __version__


def main(argv: list[str] | None = None) -> None:
    """Run the server over stdio (default) or streamable HTTP."""
    parser = argparse.ArgumentParser(prog="probo-mcp", description="Read-only MCP server for EG ProBo.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host (streamable-http only)")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (streamable-http only)")
    args = parser.parse_args(argv)

    # stdout carries the MCP protocol over stdio, so logs must go to stderr.
    logging.basicConfig(
        level=os.environ.get("PROBO_LOG_LEVEL", "WARNING").upper(),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    from .server import mcp

    if args.transport == "stdio":
        mcp.run("stdio")
    else:
        mcp.run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
