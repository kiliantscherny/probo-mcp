"""End-to-end tests through a real in-process MCP client, on both protocol eras."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import respx
from mcp import Client
from mcp.client.context import ClientRequestContext
from mcp.server.mcpserver import MCPServer
from mcp.types import (
    ElicitRequestParams,
    ElicitResult,
    PromptMessage,
    PromptReference,
    ResourceTemplateReference,
    TextContent,
    TextResourceContents,
)

from probo_mcp.config import ConfigError, Settings
from probo_mcp.server import create_server
from probo_mcp.ui import RESOURCE_URI

from .conftest import BASE, FILE_ID, MESSAGE_ID, NEWS_ID, PAGE_ID, SUBFOLDER_FILE_ID


def text(block: object) -> str:
    """The text of a content block / resource contents / prompt message, asserting its type."""
    content = getattr(block, "content", block) if isinstance(block, PromptMessage) else block
    assert isinstance(content, TextContent | TextResourceContents), type(content)
    return content.text


MODES = pytest.mark.parametrize("mode", ["auto", "legacy"])  # 2026-07-28 stateless, and 2025-11-25 handshake


async def call(server: MCPServer, tool: str, args: dict[str, Any] | None = None, *, mode: str = "auto", **kw: Any):
    async with Client(server, mode=mode, **kw) as client:
        return await client.call_tool(tool, args or {})


# -- catalogue ---------------------------------------------------------------------


async def test_server_info_and_catalogue(server: MCPServer) -> None:
    async with Client(server) as client:
        assert client.server_info is not None
        assert client.server_info.name == "probo"
        assert client.server_info.title == "ProBo"
        assert client.server_info.icons
        assert "find_documents" in (client.instructions or "")
        tools = {t.name: t for t in (await client.list_tools()).tools}
        templates = {t.uri_template for t in (await client.list_resource_templates()).resource_templates}
        prompts = {p.name for p in (await client.list_prompts()).prompts}

    assert set(tools) == {
        "open_probo_browser", "get_overview", "list_messages", "get_message", "list_news", "get_news",
        "list_documents", "recent_documents", "find_documents", "read_document", "download_document",
        "list_info_pages", "get_info_page",
    }  # fmt: skip
    for name, tool in tools.items():
        assert tool.title, name
        assert tool.annotations is not None
        assert tool.annotations.destructive_hint is False, name
        assert tool.output_schema, f"{name} should publish an output schema"
        assert tool.annotations.read_only_hint is (name != "download_document"), name
    # Injected parameters never leak into the schema the model sees.
    assert set(tools["download_document"].input_schema["properties"]) == {"document"}
    assert "ctx" not in tools["get_overview"].input_schema["properties"]
    assert tools["open_probo_browser"].meta == {"ui": {"resourceUri": RESOURCE_URI}}
    assert templates == {
        "probo://messages/{message_id}", "probo://news/{news_id}",
        "probo://documents/{document_id}", "probo://info-pages/{page_id}",
    }  # fmt: skip
    assert prompts == {"whats_new", "summarize_document", "prepare_for_general_meeting"}


# -- tools -------------------------------------------------------------------------


@MODES
async def test_overview(server: MCPServer, mode: str) -> None:
    result = await call(server, "get_overview", {"limit": 1}, mode=mode)
    assert not result.is_error
    overview = result.structured_content
    assert overview is not None
    assert overview["site"] == BASE
    assert [m["subject"] for m in overview["messages"]] == ["Bike storage keys (2)"]
    assert overview["messages"][0]["url"] == f"{BASE}/member/communication/message/{MESSAGE_ID}/change/"
    assert overview["recent_documents"][0]["name"] == "Project proposal.pdf"


@MODES
async def test_list_and_read_message(server: MCPServer, probo_site: respx.Router, mode: str) -> None:
    listing = await call(server, "list_messages", {"folder": "sent", "search": "keys", "page": 2}, mode=mode)
    assert listing.structured_content is not None
    assert len(listing.structured_content["result"]) == 2
    sent = next(c.request for c in probo_site.calls if c.request.url.path == "/member/communication/message/")
    assert dict(sent.url.params) == {"filter": "1", "q": "keys", "p": "2"}
    assert sent.headers["hx-request"] == "true"

    thread = await call(server, "get_message", {"message_id": MESSAGE_ID.upper()}, mode=mode)
    assert thread.structured_content is not None
    assert thread.structured_content["subject"] == "Bike storage keys"
    assert len(thread.structured_content["messages"]) == 2


async def test_news(server: MCPServer) -> None:
    news = await call(server, "list_news")
    assert news.structured_content is not None
    assert news.structured_content["result"][0]["id"] == NEWS_ID
    item = await call(server, "get_news", {"news_id": NEWS_ID})
    assert item.structured_content is not None
    assert item.structured_content["title"] == "Heating off tomorrow"


async def test_documents_folder_and_recent(server: MCPServer) -> None:
    folder = await call(server, "list_documents", {"order": "alphabetical"})
    assert folder.structured_content is not None
    kinds = {e["kind"] for e in folder.structured_content["entries"]}
    assert kinds == {"folder", "file"}

    recent = await call(server, "recent_documents")
    assert recent.structured_content is not None
    assert recent.structured_content["result"][0]["id"] == FILE_ID
    links = [c for c in recent.content if c.type == "resource_link"]
    assert [str(link.uri) for link in links] == [f"probo://documents/{FILE_ID}"]


@MODES
async def test_find_documents_walks_archive_with_progress(server: MCPServer, mode: str) -> None:
    events: list[tuple[float, float | None, str | None]] = []

    async def on_progress(progress: float, total: float | None, message: str | None) -> None:
        events.append((progress, total, message))

    async with Client(server, mode=mode) as client:
        result = await client.call_tool("find_documents", {"name_contains": "MINUTES"}, progress_callback=on_progress)

    assert result.structured_content is not None
    found = result.structured_content["documents"]
    assert [(d["name"], d["folder"]) for d in found] == [("Minutes 2026-05.pdf", "Board minutes")]
    assert result.structured_content["folders_scanned"] == 2  # root + subfolder; the "Tilbage" link is skipped
    assert [str(c.uri) for c in result.content if c.type == "resource_link"] == [
        f"probo://documents/{SUBFOLDER_FILE_ID}"
    ]
    assert events
    assert events[-1][0] == 2
    assert events[-1][2] == "Scanned Board minutes"


async def test_read_document_extracts_pdf_text(server: MCPServer) -> None:
    result = await call(server, "read_document", {"document": FILE_ID})
    doc = result.structured_content
    assert doc is not None
    assert doc["filename"] == "Budget 2026.pdf"
    assert "Hello from the ProBo archive" in doc["text"]


async def test_info_pages(server: MCPServer) -> None:
    pages = await call(server, "list_info_pages")
    assert pages.structured_content is not None
    assert [p["title"] for p in pages.structured_content["result"]] == ["House rules", "Contacts"]
    page = await call(server, "get_info_page", {"page_id": PAGE_ID})
    assert page.structured_content is not None
    assert "No grilling" in page.structured_content["content_markdown"]


async def test_open_browser_returns_overview(server: MCPServer) -> None:
    result = await call(server, "open_probo_browser", {"view": "documents"})
    assert result.structured_content is not None
    assert result.structured_content["site"] == BASE


# -- download + elicitation -----------------------------------------------------------------


def _always_ask(settings: Settings) -> Settings:
    return replace(settings, confirm_download_mb=0)


@MODES
async def test_small_download_saves_without_asking(server: MCPServer, settings: Settings, mode: str) -> None:
    result = await call(server, "download_document", {"document": FILE_ID}, mode=mode)
    saved = result.structured_content
    assert saved is not None
    assert Path(saved["path"]) == (settings.download_dir / "Budget 2026.pdf").resolve()
    assert Path(saved["path"]).read_bytes().startswith(b"%PDF")


@MODES
async def test_large_download_asks_and_uses_chosen_name(
    settings: Settings, probo_site: respx.Router, mode: str
) -> None:
    asked: list[str] = []

    async def accept(context: ClientRequestContext, params: ElicitRequestParams) -> ElicitResult:
        asked.append(params.message)
        return ElicitResult(action="accept", content={"filename": "renamed.pdf"})

    server = create_server(lambda: _always_ask(settings))
    result = await call(server, "download_document", {"document": FILE_ID}, mode=mode, elicitation_callback=accept)
    assert asked
    assert "Budget 2026.pdf" in asked[0]
    assert result.structured_content is not None
    assert result.structured_content["filename"] == "renamed.pdf"
    assert (settings.download_dir / "renamed.pdf").exists()


async def test_large_download_declined_saves_nothing(settings: Settings, probo_site: respx.Router) -> None:
    async def decline(context: ClientRequestContext, params: ElicitRequestParams) -> ElicitResult:
        return ElicitResult(action="decline")

    server = create_server(lambda: _always_ask(settings))
    result = await call(server, "download_document", {"document": FILE_ID}, elicitation_callback=decline)
    assert result.is_error
    assert not settings.download_dir.exists()


async def test_large_download_without_elicitation_support_proceeds(
    settings: Settings, probo_site: respx.Router
) -> None:
    server = create_server(lambda: _always_ask(settings))
    result = await call(server, "download_document", {"document": FILE_ID})  # no elicitation_callback
    assert not result.is_error
    assert (settings.download_dir / "Budget 2026.pdf").exists()


# -- errors -----------------------------------------------------------------------------


async def test_invalid_id_is_a_tool_error(server: MCPServer) -> None:
    result = await call(server, "get_message", {"message_id": "../../password_change"})
    assert result.is_error
    assert "expected a UUID" in text(result.content[0])


async def test_disallowed_attachment_path_is_refused(server: MCPServer, probo_site: respx.Router) -> None:
    path = f"/member/communication/message/toggle_subscription/{MESSAGE_ID}/"
    result = await call(server, "read_document", {"document": path})
    assert result.is_error
    assert "not an allowlisted" in text(result.content[0])
    assert not any("toggle_subscription" in str(c.request.url) for c in probo_site.calls)


async def test_missing_configuration_explains_what_to_set(probo_site: respx.Router) -> None:
    def unconfigured() -> Settings:
        raise ConfigError("Missing required setting(s): PROBO_BASE_URL")

    result = await call(create_server(unconfigured), "get_overview")
    assert result.is_error
    assert "not configured" in text(result.content[0])
    assert "PROBO_BASE_URL" in text(result.content[0])


async def test_unknown_document_is_a_tool_error(server: MCPServer) -> None:
    result = await call(server, "read_document", {"document": "99999999-9999-9999-9999-999999999999"})
    assert result.is_error
    assert "Not found" in text(result.content[0])


# -- resources, completions, prompts -------------------------------------------------------


@MODES
async def test_resources(server: MCPServer, mode: str) -> None:
    async with Client(server, mode=mode) as client:
        message = await client.read_resource(f"probo://messages/{MESSAGE_ID}")
        news = await client.read_resource(f"probo://news/{NEWS_ID}")
        doc = await client.read_resource(f"probo://documents/{FILE_ID}")
        page = await client.read_resource(f"probo://info-pages/{PAGE_ID}")
    texts = {name: text(r.contents[0]) for name, r in [("m", message), ("n", news), ("d", doc), ("p", page)]}
    assert texts["m"].startswith("# Bike storage keys")
    assert "## Jane Resident · 30 Sept 2026 · 19:15" in texts["m"]
    assert "## Comments" in texts["n"]
    assert texts["d"].startswith("# Budget 2026.pdf")
    assert "Hello from the ProBo archive" in texts["d"]
    assert "No grilling" in texts["p"]
    assert message.contents[0].mime_type == "text/markdown"


async def test_unknown_resource_id_is_not_found(server: MCPServer) -> None:
    from mcp.shared.exceptions import MCPError

    async with Client(server) as client:
        with pytest.raises(MCPError):
            await client.read_resource("probo://messages/not-a-uuid")


async def test_ui_resource_inlines_the_apps_sdk(server: MCPServer) -> None:
    async with Client(server) as client:
        ui = await client.read_resource(RESOURCE_URI)
    html = text(ui.contents[0])
    assert ui.contents[0].mime_type == "text/html;profile=mcp-app"
    assert "const ExtApps={" in html
    assert "App:" in html
    assert "__EXT_APPS_BUNDLE__" not in html
    assert "</script" not in html.split('<script type="module">', 1)[1].rsplit("</script>", 1)[0]


async def test_completions(server: MCPServer) -> None:
    doc_ref = ResourceTemplateReference(type="ref/resource", uri="probo://documents/{document_id}")
    async with Client(server) as client:
        by_name = await client.complete(doc_ref, {"name": "document_id", "value": "proposal"})
        by_prefix = await client.complete(doc_ref, {"name": "document_id", "value": FILE_ID[:6]})
        messages = await client.complete(
            ResourceTemplateReference(type="ref/resource", uri="probo://messages/{message_id}"),
            {"name": "message_id", "value": "jane"},
        )
        language = await client.complete(
            PromptReference(type="ref/prompt", name="whats_new"), {"name": "language", "value": "d"}
        )
        unknown = await client.complete(
            PromptReference(type="ref/prompt", name="whats_new"), {"name": "days", "value": ""}
        )
    assert by_name.completion.values == [FILE_ID]
    assert by_prefix.completion.values == [FILE_ID]
    assert messages.completion.values == [MESSAGE_ID]
    assert language.completion.values == ["Dansk", "Deutsch"]
    assert unknown.completion.values == []


async def test_completions_degrade_when_unconfigured(probo_site: respx.Router) -> None:
    def unconfigured() -> Settings:
        raise ConfigError("nope")

    async with Client(create_server(unconfigured)) as client:
        result = await client.complete(
            ResourceTemplateReference(type="ref/resource", uri="probo://news/{news_id}"),
            {"name": "news_id", "value": ""},
        )
    assert result.completion.values == []


async def test_prompts(server: MCPServer) -> None:
    async with Client(server) as client:
        whats_new = await client.get_prompt("whats_new", {"days": "14", "language": "Dansk"})
        summary = await client.get_prompt("summarize_document", {"document_id": FILE_ID})
        meeting = await client.get_prompt("prepare_for_general_meeting", {})
    briefing = text(whats_new.messages[0])
    assert "last 14 days" in briefing
    assert "added_within_days=14" in briefing
    assert "Answer in Dansk" in briefing
    assert f"probo://documents/{FILE_ID}" in text(summary.messages[0])
    assert "generalforsamling" in text(meeting.messages[0])
