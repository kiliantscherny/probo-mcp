"""ProBo operations shared by tools, resources, prompts and the UI.

`ProboService` combines the read-only `ProboClient` with the pure HTML parsers
and adds browser URLs. It knows nothing about MCP, so it is easy to test.
"""

from __future__ import annotations

import io
import logging
import re
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import anyio.to_thread

from . import parsers
from .client import DownloadedFile, FileInfo, ProboClient, download_path, require_uuid
from .config import Settings
from .models import (
    DocumentFolder,
    DocumentSearchResult,
    DocumentText,
    FoundDocument,
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

logger = logging.getLogger(__name__)

MessageFolder = Literal["inbox", "sent", "archive", "archived_notifications", "drafts"]
DocumentOrder = Literal["date", "alphabetical", "created"]

MESSAGE_FOLDERS: dict[str, str | None] = {
    "inbox": None,
    "sent": "1",
    "archive": "0",
    "archived_notifications": "4",
    "drafts": "3",
}

ProgressCallback = Callable[[int, int, str], Awaitable[None]]


def _message_url(message_id: str) -> str:
    return f"/member/communication/message/{message_id}/change/"


def _news_url(news_id: str) -> str:
    return f"/member/communication/news/{news_id}/view/"


def _folder_url(folder_id: str) -> str:
    return f"/member/document_archive/member/{folder_id}/?m=Member"


def _file_url(document_id: str) -> str:
    return f"/member/download_file_landing/document_archive/Member/{document_id}/"


def _info_page_url(page_id: str) -> str:
    return f"/member/communities/page/{page_id}/view/"


class ProboService:
    """High-level, read-only operations against one ProBo site."""

    def __init__(self, client: ProboClient, settings: Settings):
        """Wrap a client; `settings` controls limits and the download directory."""
        self.client = client
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings) -> ProboService:
        """Create a service with a fresh client for ``settings``."""
        client = ProboClient(
            settings.base_url, settings.username, settings.password, cache_seconds=settings.cache_seconds
        )
        return cls(client, settings)

    async def aclose(self) -> None:
        """Release network resources."""
        await self.client.aclose()

    def _url(self, path: str) -> str:
        return self.client.web_url(path)

    # -- messages ------------------------------------------------------------

    async def list_messages(
        self, folder: MessageFolder = "inbox", search: str | None = None, page: int = 1
    ) -> list[MessageSummary]:
        """List message threads in a folder, newest first."""
        html = await self.client.get_html(
            "/member/communication/message/",
            {"filter": MESSAGE_FOLDERS[folder] or "", "q": search or "", "p": str(max(page, 1))},
            htmx=True,
        )
        return [m.model_copy(update={"url": self._url(_message_url(m.id))}) for m in parsers.parse_message_list(html)]

    async def get_message(self, message_id: str) -> MessageThread:
        """Get a full thread. Opening a thread may mark it as read in ProBo."""
        message_id = require_uuid(message_id, "message id")
        html = await self.client.get_html(_message_url(message_id))
        thread = parsers.parse_message_thread(html, message_id)
        return thread.model_copy(update={"url": self._url(_message_url(message_id))})

    # -- news ----------------------------------------------------------------

    async def list_news(self, search: str | None = None, page: int = 1) -> list[NewsSummary]:
        """List news posts, newest first."""
        html = await self.client.get_html(
            "/member/communication/news/", {"q": search or "", "p": str(max(page, 1))}, htmx=True
        )
        return [n.model_copy(update={"url": self._url(_news_url(n.id))}) for n in parsers.parse_news_list(html)]

    async def get_news(self, news_id: str) -> NewsItem:
        """Get a news post with comments."""
        news_id = require_uuid(news_id, "news id")
        item = parsers.parse_news_item(await self.client.get_html(_news_url(news_id)), news_id)
        return item.model_copy(update={"url": self._url(_news_url(news_id))})

    # -- documents -------------------------------------------------------------

    async def list_documents(self, folder_id: str | None = None, order: DocumentOrder = "date") -> DocumentFolder:
        """List one archive folder (the root when ``folder_id`` is None)."""
        params: dict[str, str] = {"ordering": order}
        path = "/member/document_archive/member/"
        if folder_id:
            folder_id = require_uuid(folder_id, "folder id")
            path = f"{path}{folder_id}/"
            params["m"] = "Member"
        folder = parsers.parse_document_folder(await self.client.get_html(path, params), folder_id)
        entries = [
            e.model_copy(update={"url": self._url(_file_url(e.id) if e.kind == "file" else _folder_url(e.id))})
            for e in folder.entries
        ]
        return folder.model_copy(update={"entries": entries})

    async def recent_documents(self) -> list[RecentDocument]:
        """The archive's "recently added" widget (usually only a handful of entries)."""
        html = await self.client.get_html("/member/document_archive/member/")
        return [d.model_copy(update={"url": self._url(_file_url(d.id))}) for d in parsers.parse_recent_documents(html)]

    async def find_documents(
        self,
        *,
        added_within_days: int | None = None,
        name_contains: str | None = None,
        folder_id: str | None = None,
        max_folders: int = 200,
        progress: ProgressCallback | None = None,
        now: datetime | None = None,
    ) -> DocumentSearchResult:
        """Walk the archive (breadth-first) and return files matching the filters, newest first."""
        cutoff = (now or datetime.now()) - timedelta(days=added_within_days) if added_within_days else None
        needle = (name_contains or "").casefold().strip()
        queue: deque[tuple[str | None, list[str]]] = deque([(folder_id, [])])
        visited: set[str | None] = set()
        found: list[FoundDocument] = []
        files_scanned = 0
        unparsed_dates = 0

        while queue and len(visited) < max_folders:
            current, trail = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            folder = await self.list_documents(current, order="created")
            for entry in folder.entries:
                if entry.kind == "folder":
                    queue.append((entry.id, [*trail, entry.name]))
                    continue
                files_scanned += 1
                added = parsers.parse_probo_date(entry.added_text) or parsers.parse_probo_date(entry.date_text)
                if cutoff is not None:
                    if added is None:
                        unparsed_dates += 1
                        continue
                    if added < cutoff:
                        continue
                if needle and needle not in entry.name.casefold():
                    continue
                found.append(
                    FoundDocument(
                        id=entry.id,
                        name=entry.name,
                        folder="/".join(trail),
                        date_text=entry.date_text,
                        added_text=entry.added_text,
                        added=added,
                        url=entry.url,
                    )
                )
            if progress is not None:
                label = "/".join(trail) or "archive root"
                await progress(len(visited), len(visited) + len(queue), f"Scanned {label}")

        found.sort(key=lambda d: d.added or datetime.min, reverse=True)
        notes = []
        if queue:
            notes.append(f"Stopped after {max_folders} folders; narrow the search with folder_id.")
        if unparsed_dates:
            notes.append(f"{unparsed_dates} file(s) were skipped because their date could not be parsed.")
        return DocumentSearchResult(
            documents=found, folders_scanned=len(visited), files_scanned=files_scanned, note=" ".join(notes)
        )

    async def file_info(self, document: str) -> FileInfo:
        """Name, type and size of a document without downloading it."""
        return await self.client.file_info(download_path(document))

    async def download(self, document: str) -> DownloadedFile:
        """Download a document by id or attachment path."""
        return await self.client.download(download_path(document))

    async def read_document(self, document: str) -> DocumentText:
        """Extract the text of a PDF or plain-text document."""
        path = download_path(document)
        f = await self.client.download(path)
        text, note = extract_text(f)
        limit = self.settings.max_document_chars
        truncated = bool(text and len(text) > limit)
        if text and truncated:
            text = text[:limit]
            note = (note + " " if note else "") + f"Truncated to {limit} characters."
        return DocumentText(
            id=path,
            filename=f.filename,
            content_type=f.content_type,
            size_bytes=len(f.content),
            text=text,
            truncated=truncated,
            note=note,
        )

    async def save_document(self, document: str, filename: str | None = None) -> SavedFile:
        """Download a document into the configured download directory."""
        f = await self.download(document)
        target = self.settings.download_dir / safe_filename(filename or f.filename)
        await anyio.to_thread.run_sync(_write_file, target, f.content)
        logger.info("Saved %s (%d bytes)", target, len(f.content))
        return SavedFile(path=str(target), filename=target.name, size_bytes=len(f.content), content_type=f.content_type)

    # -- info pages & overview ---------------------------------------------------

    async def list_info_pages(self) -> list[InfoPageLink]:
        """The association's information pages."""
        links = parsers.parse_info_page_links(await self.client.get_html("/member/"))
        return [p.model_copy(update={"url": self._url(_info_page_url(p.id))}) for p in links]

    async def get_info_page(self, page_id: str) -> InfoPage:
        """One information page as Markdown."""
        page_id = require_uuid(page_id, "page id")
        page = parsers.parse_info_page(await self.client.get_html(_info_page_url(page_id)), page_id)
        return page.model_copy(update={"url": self._url(_info_page_url(page_id))})

    async def overview(self, limit: int = 5) -> Overview:
        """Latest inbox messages, news and recently added documents."""
        return Overview(
            site=self.client.base_url,
            messages=(await self.list_messages())[:limit],
            news=(await self.list_news())[:limit],
            recent_documents=(await self.recent_documents())[:limit],
        )


def extract_text(f: DownloadedFile) -> tuple[str | None, str]:
    """Return ``(text, note)`` for a downloaded file."""
    if f.content_type == "application/pdf" or f.filename.lower().endswith(".pdf"):
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(io.BytesIO(f.content))
            text = "\n\n".join((p.extract_text() or "") for p in reader.pages).strip()
        except PdfReadError as e:
            return None, f"Could not read the PDF: {e}"
        if not text:
            return None, "The PDF has no extractable text (probably scanned). Use download_document to get the file."
        return text, ""
    if f.content_type.startswith("text/"):
        return f.content.decode("utf-8", errors="replace"), ""
    return None, f"Text extraction is not supported for {f.content_type}. Use download_document to save the file."


def _write_file(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def safe_filename(name: str) -> str:
    """Strip path separators and leading dots so a server-supplied name can't escape the download dir."""
    cleaned = re.sub(r"[/\\\x00-\x1f]", "_", name).strip().lstrip(".")
    return cleaned or "document"
