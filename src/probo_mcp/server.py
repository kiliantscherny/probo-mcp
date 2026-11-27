"""Assemble the probo MCP server."""

import base64
import os
from collections.abc import Callable
from importlib.resources import files

from mcp.server.caching import CacheHint
from mcp.server.mcpserver import Icon, MCPServer

from . import __version__, prompts, resources, tools
from .config import Settings
from .state import AppState, lifespan_for
from .ui import apps

INSTRUCTIONS = """\
Read-only access to an EG ProBo (probo.dk) owners'/residents' association portal: \
messages, news, the document archive and information pages. Content is usually in Danish.

- For "what's new" (also "hvad er nyt", "nyt fra ejerforeningen/foreningen/bestyrelsen") call whats_new: \
it returns everything not yet in the local archive, already fetched in full, and remembers it. If \
`remaining` > 0, call it again. If a call failed after fetching, whats_new(repeat_last=true) returns that \
result again. get_overview is a quick peek that remembers nothing.
- To download or back up older items (all past news, the whole document archive) call fetch_history \
until `remaining` is 0. It saves files and returns a short list, not their content.
- Use list_* tools to find ids, then get_* / read_document.
- For "documents added in the last N days" use find_documents(added_within_days=N): \
recent_documents only shows a handful.
- Attachment `path` values from get_message / get_news / get_info_page work with read_document.
- Scanned PDFs have no text: read_document then attaches the pages as images for you to read.
- Every item has a `url` the user can open in their browser.
- Nothing can be sent, changed or deleted in ProBo through this server.
"""

_HOUR_MS = 3_600_000


def _icon() -> Icon:
    svg = (files(__package__) / "assets" / "icon.svg").read_bytes()
    return Icon(src=f"data:image/svg+xml;base64,{base64.b64encode(svg).decode()}", mime_type="image/svg+xml")


def create_server(settings_factory: Callable[[], Settings] = Settings.from_env) -> MCPServer:
    """Build the server. Tests pass their own ``settings_factory``."""
    state = AppState(settings_factory)
    mcp = MCPServer(
        "probo",
        title="ProBo",
        description="Read-only access to EG ProBo owners' association portals",
        instructions=INSTRUCTIONS,
        version=__version__,
        website_url="https://kiliantscherny.github.io/probo-mcp/",
        icons=[_icon()],
        lifespan=lifespan_for(state),
        log_level=os.environ.get("PROBO_LOG_LEVEL", "WARNING").upper(),  # ty: ignore[invalid-argument-type]
        extensions=[apps],
        cache_hints={
            # The tool/prompt/template catalogue only changes with a new release.
            "tools/list": CacheHint(ttl_ms=_HOUR_MS, scope="public"),
            "prompts/list": CacheHint(ttl_ms=_HOUR_MS, scope="public"),
            "resources/templates/list": CacheHint(ttl_ms=_HOUR_MS, scope="public"),
            # Content is per-user and changes, so cache briefly and privately.
            "resources/read": CacheHint(ttl_ms=60_000, scope="private"),
        },
        # Read-only server that fetches on demand: nothing to push to subscribers.
        subscriptions=False,
    )
    tools.register(mcp)
    resources.register(mcp, state)
    prompts.register(mcp)
    return mcp


mcp = create_server()
