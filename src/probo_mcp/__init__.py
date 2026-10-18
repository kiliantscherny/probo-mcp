"""Read-only MCP server for EG ProBo owners' association portals."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("probo-mcp")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without install
    __version__ = "0.0.0"
