"""MCP resources: ProBo content addressable by ``probo://`` URIs, with argument completion."""

import logging
from collections.abc import Awaitable, Callable

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ResourceNotFoundError
from mcp.types import (
    Completion,
    CompletionArgument,
    CompletionContext,
    PromptReference,
    ResourceTemplateReference,
)

from .client import ProboError
from .config import ConfigError
from .markdown import document_markdown, info_page_markdown, news_markdown, thread_markdown
from .service import ProboService
from .state import AppState, service_from

logger = logging.getLogger(__name__)

MAX_COMPLETIONS = 20


async def _read[T](ctx: Context, call: Callable[[ProboService], Awaitable[T]], what: str) -> T:
    """Run a service call, mapping failures to resource errors (-32602 for unknown ids)."""
    try:
        return await call(service_from(ctx))
    except ValueError as e:
        raise ResourceNotFoundError(str(e)) from e
    except ConfigError as e:
        raise ResourceError(f"probo-mcp is not configured: {e}") from e
    except ProboError as e:
        if "Not found" in str(e):
            raise ResourceNotFoundError(f"No such {what}") from e
        raise ResourceError(str(e)) from e


def register(mcp: MCPServer, state: AppState) -> None:
    """Register resource templates and the completion handler on ``mcp``."""

    @mcp.resource(
        "probo://messages/{message_id}",
        name="message",
        title="ProBo message thread",
        description="A message thread rendered as Markdown.",
        mime_type="text/markdown",
    )
    async def message_resource(message_id: str, ctx: Context) -> str:
        thread = await _read(ctx, lambda s: s.get_message(message_id), "message")
        return thread_markdown(thread)

    @mcp.resource(
        "probo://news/{news_id}",
        name="news",
        title="ProBo news post",
        description="A news post and its comments as Markdown.",
        mime_type="text/markdown",
    )
    async def news_resource(news_id: str, ctx: Context) -> str:
        return news_markdown(await _read(ctx, lambda s: s.get_news(news_id), "news post"))

    @mcp.resource(
        "probo://documents/{document_id}",
        name="document",
        title="ProBo document",
        description="A document from the archive: metadata and extracted text as Markdown.",
        mime_type="text/markdown",
    )
    async def document_resource(document_id: str, ctx: Context) -> str:
        return document_markdown(await _read(ctx, lambda s: s.read_document(document_id), "document"))

    @mcp.resource(
        "probo://info-pages/{page_id}",
        name="info-page",
        title="ProBo info page",
        description="One of the association's information pages as Markdown.",
        mime_type="text/markdown",
    )
    async def info_page_resource(page_id: str, ctx: Context) -> str:
        return info_page_markdown(await _read(ctx, lambda s: s.get_info_page(page_id), "info page"))

    @mcp.completion()
    async def complete(
        ref: ResourceTemplateReference | PromptReference,
        argument: CompletionArgument,
        context: CompletionContext | None,
    ) -> Completion | None:
        return await _complete(state, ref, argument)


LANGUAGES = ["English", "Dansk", "Deutsch", "Svenska", "Norsk", "Français", "Español", "Polski", "Українська"]


async def _complete(
    state: AppState, ref: ResourceTemplateReference | PromptReference, argument: CompletionArgument
) -> Completion | None:
    if argument.name == "language":
        typed = argument.value.casefold()
        return Completion(values=[lang for lang in LANGUAGES if lang.casefold().startswith(typed)])

    candidates_for = {
        "message_id": _message_candidates,
        "news_id": _news_candidates,
        "document_id": _document_candidates,
        "page_id": _page_candidates,
    }.get(argument.name)
    if candidates_for is None:
        return None
    try:
        candidates = await candidates_for(state.service())
    except (ConfigError, ProboError, ValueError) as e:
        logger.info("Completion unavailable: %s", e)
        return Completion(values=[])

    # Values must be ids, but people type names: match on either, keep ProBo's (newest-first) order.
    typed = argument.value.casefold().strip()
    matches = [cid for cid, label in candidates if not typed or cid.startswith(typed) or typed in label.casefold()]
    return Completion(values=matches[:MAX_COMPLETIONS], total=len(matches), has_more=len(matches) > MAX_COMPLETIONS)


async def _message_candidates(service: ProboService) -> list[tuple[str, str]]:
    return [(m.id, f"{m.sender} {m.subject}") for m in await service.list_messages()]


async def _news_candidates(service: ProboService) -> list[tuple[str, str]]:
    return [(n.id, n.subject) for n in await service.list_news()]


async def _document_candidates(service: ProboService) -> list[tuple[str, str]]:
    recent = [(d.id, d.name) for d in await service.recent_documents()]
    root = [(e.id, e.name) for e in (await service.list_documents()).entries if e.kind == "file"]
    return list(dict.fromkeys(recent + root))


async def _page_candidates(service: ProboService) -> list[tuple[str, str]]:
    return [(p.id, p.title) for p in await service.list_info_pages()]
