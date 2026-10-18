"""MCP tools. Every tool is read-only with respect to ProBo."""

import logging
from typing import Annotated

from mcp.server.mcpserver import Context, Elicit, MCPServer, Resolve
from mcp.types import CallToolResult, ResourceLink, TextContent, ToolAnnotations
from pydantic import BaseModel, Field, create_model

from .models import (
    DocumentFolder,
    DocumentSearchResult,
    DocumentText,
    InfoPage,
    InfoPageLink,
    MessageSummary,
    MessageThread,
    NewsItem,
    NewsSummary,
    Overview,
    RecentDocument,
    SavedFile,
)
from .service import DocumentOrder, MessageFolder
from .state import service_from, user_errors

logger = logging.getLogger(__name__)

#: Reads remote data; repeated calls are safe; never changes anything in ProBo.
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True)


def _document_link(doc_id: str, name: str) -> ResourceLink:
    return ResourceLink(
        type="resource_link",
        uri=f"probo://documents/{doc_id}",
        name=name,
        title=name,
        mime_type="text/markdown",
        description="Extracted text of this ProBo document",
    )


# -- overview ------------------------------------------------------------------


@user_errors
async def get_overview(ctx: Context, limit: Annotated[int, Field(ge=1, le=50)] = 5) -> Overview:
    """What's new: the latest inbox messages, news posts and recently added documents."""
    return await service_from(ctx).overview(limit)


# -- messages ------------------------------------------------------------------


@user_errors
async def list_messages(
    ctx: Context,
    folder: MessageFolder = "inbox",
    search: Annotated[str | None, Field(description="Free-text search, as in ProBo's search box.")] = None,
    page: Annotated[int, Field(ge=1, description="1-based page; an empty list means you are past the end.")] = 1,
) -> list[MessageSummary]:
    """List message threads in a folder, newest first."""
    return await service_from(ctx).list_messages(folder, search, page)


@user_errors
async def get_message(ctx: Context, message_id: str) -> MessageThread:
    """Get a full message thread: every reply as Markdown, plus attachment paths.

    Note: like in the browser, opening a thread may mark it as read in ProBo.
    """
    return await service_from(ctx).get_message(message_id)


# -- news ----------------------------------------------------------------------


@user_errors
async def list_news(
    ctx: Context,
    search: str | None = None,
    page: Annotated[int, Field(ge=1)] = 1,
) -> list[NewsSummary]:
    """List the association's news posts, newest first."""
    return await service_from(ctx).list_news(search, page)


@user_errors
async def get_news(ctx: Context, news_id: str) -> NewsItem:
    """Get a news post's content and comments as Markdown."""
    return await service_from(ctx).get_news(news_id)


# -- documents -----------------------------------------------------------------


@user_errors
async def list_documents(
    ctx: Context,
    folder_id: Annotated[str | None, Field(description="Folder id; omit for the archive root.")] = None,
    order: DocumentOrder = "date",
) -> DocumentFolder:
    """List the folders and files in one folder of the document archive."""
    return await service_from(ctx).list_documents(folder_id, order)


@user_errors
async def recent_documents(ctx: Context) -> Annotated[CallToolResult, list[RecentDocument]]:
    """List the documents most recently added to the archive (ProBo shows only a handful).

    For "everything added in the last N days", use find_documents instead.
    """
    docs = await service_from(ctx).recent_documents()
    return CallToolResult(
        content=[
            TextContent(type="text", text=f"{len(docs)} recently added document(s)."),
            *(_document_link(d.id, d.name) for d in docs),
        ],
        structured_content={"result": [d.model_dump(mode="json") for d in docs]},
    )


@user_errors
async def find_documents(
    ctx: Context,
    added_within_days: Annotated[
        int | None, Field(ge=1, description="Only files added in the last N days (e.g. 7).")
    ] = None,
    name_contains: Annotated[str | None, Field(description="Case-insensitive file-name filter.")] = None,
    folder_id: Annotated[str | None, Field(description="Start from this folder instead of the root.")] = None,
) -> Annotated[CallToolResult, DocumentSearchResult]:
    """Search the whole document archive (all sub-folders) by upload date and/or file name.

    Walks every folder, so it takes a few seconds; progress is reported as it goes.
    """

    async def progress(done: int, total: int, message: str) -> None:
        await ctx.report_progress(done, total, message)

    result = await service_from(ctx).find_documents(
        added_within_days=added_within_days, name_contains=name_contains, folder_id=folder_id, progress=progress
    )
    summary = f"Found {len(result.documents)} document(s) in {result.folders_scanned} folder(s). {result.note}".strip()
    return CallToolResult(
        content=[TextContent(type="text", text=summary), *(_document_link(d.id, d.name) for d in result.documents)],
        structured_content=result.model_dump(mode="json"),
    )


@user_errors
async def read_document(
    ctx: Context,
    document: Annotated[str, Field(description="A document id, or an attachment `path` from another tool.")],
) -> DocumentText:
    """Fetch a document and return its text (PDF and plain-text files)."""
    return await service_from(ctx).read_document(document)


class DownloadConfirmation(BaseModel):
    """What the user chose when asked to confirm a large download."""

    filename: str


async def confirm_large_download(document: str, ctx: Context) -> Elicit[DownloadConfirmation] | DownloadConfirmation:
    """Ask the user before saving a large file, when the client supports elicitation.

    Small files, and clients without elicitation support, proceed without asking.
    """
    service = service_from(ctx)
    info = await service.file_info(document)
    limit = service.settings.confirm_download_mb * 1024 * 1024
    capabilities = ctx.client_capabilities
    can_ask = capabilities is not None and capabilities.elicitation is not None
    if not can_ask or info.size_bytes is None or info.size_bytes <= limit:
        return DownloadConfirmation(filename=info.filename)
    form = create_model(
        "DownloadConfirmation",
        __base__=DownloadConfirmation,
        filename=(str, Field(default=info.filename, title="Save as", description="File name in the download folder")),
    )
    size_mb = info.size_bytes / 1024 / 1024
    return Elicit(f"{info.filename} is {size_mb:.0f} MB. Save it to {service.settings.download_dir}?", form)


@user_errors
async def download_document(
    ctx: Context,
    document: Annotated[str, Field(description="A document id, or an attachment `path` from another tool.")],
    confirmation: Annotated[DownloadConfirmation, Resolve(confirm_large_download)],
) -> SavedFile:
    """Save a document to the local download folder and return where it was saved.

    Only writes to this computer; nothing changes in ProBo. Large files ask for confirmation first.
    """
    return await service_from(ctx).save_document(document, confirmation.filename)


# -- info pages ------------------------------------------------------------------


@user_errors
async def list_info_pages(ctx: Context) -> list[InfoPageLink]:
    """List the association's information pages (house rules, contacts, practical info...)."""
    return await service_from(ctx).list_info_pages()


@user_errors
async def get_info_page(ctx: Context, page_id: str) -> InfoPage:
    """Get an information page's content as Markdown."""
    return await service_from(ctx).get_info_page(page_id)


TOOLS = [
    (get_overview, "What's new in ProBo"),
    (list_messages, "List messages"),
    (get_message, "Read message thread"),
    (list_news, "List news"),
    (get_news, "Read news post"),
    (list_documents, "Browse document archive"),
    (recent_documents, "Recently added documents"),
    (find_documents, "Search document archive"),
    (read_document, "Read document text"),
    (list_info_pages, "List info pages"),
    (get_info_page, "Read info page"),
]


def register(mcp: MCPServer) -> None:
    """Register all tools on ``mcp``."""
    for fn, title in TOOLS:
        mcp.add_tool(fn, title=title, annotations=READ_ONLY)
    # Writes a local file, but never modifies ProBo; saving twice overwrites the same file.
    mcp.add_tool(
        download_document,
        title="Download document",
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True
        ),
    )
