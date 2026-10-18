"""Interactive ProBo browser, served as an MCP App (``ui://`` resource rendered by the client).

The page uses the official MCP Apps JS SDK (``@modelcontextprotocol/ext-apps``),
vendored as a single self-contained ES module so no Node toolchain is needed.
It is inlined into the HTML because MCP App iframes are sandboxed and should
not need network access beyond calling this server's tools through the host.
"""

import re
from functools import cache
from importlib.resources import files
from typing import Annotated, Literal

from mcp.server.apps import Apps
from mcp.server.mcpserver import Context
from pydantic import Field

from ..models import Overview
from ..state import service_from, user_errors
from ..tools import READ_ONLY

RESOURCE_URI = "ui://probo/browser.html"
EXT_APPS_VERSION = "2.0.3"
_PLACEHOLDER = "/*__EXT_APPS_BUNDLE__*/"


@cache
def browser_html() -> str:
    """The app page with the MCP Apps SDK inlined (exports exposed as ``ExtApps``)."""
    here = files(__package__)
    bundle = (here / "vendor" / f"ext-apps-app-{EXT_APPS_VERSION}.js").read_text(encoding="utf-8")
    exports = re.search(r"export\{([^}]*)\};?\s*$", bundle)
    if exports is None:  # pragma: no cover - guards against a changed vendored file
        raise RuntimeError("Unexpected ext-apps bundle format: no trailing export list")
    mapping = ",".join(
        f"{(alias or local).strip()}:{local.strip()}"
        for local, _, alias in (item.strip().partition(" as ") for item in exports.group(1).split(","))
    )
    inlined = bundle[: exports.start()] + f"const ExtApps={{{mapping}}};"
    # Inline <script> content must not contain "</script" (it would close the tag early).
    inlined = re.sub(r"</(script)", r"<\\/\1", inlined, flags=re.IGNORECASE)
    page = (here / "browser.html").read_text(encoding="utf-8")
    return page.replace(_PLACEHOLDER, inlined)


apps = Apps()


@apps.tool(resource_uri=RESOURCE_URI, title="Open ProBo browser", annotations=READ_ONLY)
@user_errors
async def open_probo_browser(
    ctx: Context,
    view: Annotated[
        Literal["overview", "messages", "news", "documents", "pages"],
        Field(description="Which tab to open."),
    ] = "overview",
) -> Overview:
    """Open an interactive ProBo browser in the chat (messages, news, documents, info pages).

    Clients without MCP Apps support get the same overview as get_overview.
    """
    return await service_from(ctx).overview(limit=8)


apps.add_html_resource(
    RESOURCE_URI,
    browser_html(),
    name="probo-browser",
    title="ProBo browser",
    description="Interactive browser for ProBo messages, news, documents and info pages.",
    prefers_border=True,
)
