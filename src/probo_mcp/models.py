"""Structured data returned by the MCP tools (published as JSON output schemas)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Attachment(BaseModel):
    """A file attached to a message, news post or info page."""

    name: str
    path: str = Field(description="Pass to read_document / download_document.")


class MessageSummary(BaseModel):
    """One row of a message folder."""

    id: str
    sender: str
    subject: str
    date_text: str = Field(description="Date exactly as ProBo shows it.")
    date: datetime | None = Field(default=None, description="Parsed date, when the format is recognised.")
    url: str = ""


class MessageCard(BaseModel):
    """One message within a thread."""

    sender: str
    date_text: str
    date: datetime | None = None
    recipients: str = ""
    body_markdown: str
    attachments: list[Attachment] = []


class MessageThread(BaseModel):
    """A full message thread."""

    id: str
    subject: str
    messages: list[MessageCard]
    url: str = ""


class NewsSummary(BaseModel):
    """One row of the news list."""

    id: str
    subject: str
    date_text: str
    date: datetime | None = None
    comments: str = ""
    url: str = ""


class NewsItem(BaseModel):
    """A news post with its comments."""

    id: str
    title: str = ""
    date_text: str = ""
    date: datetime | None = None
    content_markdown: str
    comments_markdown: str = ""
    attachments: list[Attachment] = []
    url: str = ""


class DocumentEntry(BaseModel):
    """A folder or file in the document archive."""

    kind: Literal["folder", "file"]
    id: str
    name: str
    date_text: str = ""
    date: datetime | None = None
    added_text: str = Field(default="", description="When the entry was added to the archive, as shown.")
    url: str = ""


class DocumentFolder(BaseModel):
    """The contents of one archive folder."""

    folder_id: str | None
    path: list[str]
    entries: list[DocumentEntry]


class RecentDocument(BaseModel):
    """An entry in the archive's "recently added" widget."""

    id: str
    name: str
    folder: str = ""
    date_text: str
    date: datetime | None = None
    url: str = ""


class FoundDocument(BaseModel):
    """A file found by walking the whole archive."""

    id: str
    name: str
    folder: str = Field(description="Folder path, e.g. 'Meetings/2026'.")
    date_text: str = ""
    added_text: str = ""
    added: datetime | None = None
    url: str = ""


class DocumentSearchResult(BaseModel):
    """Result of find_documents."""

    documents: list[FoundDocument]
    folders_scanned: int
    files_scanned: int
    note: str = ""


class InfoPageLink(BaseModel):
    """An information page in the association's menu."""

    id: str
    title: str
    url: str = ""


class InfoPage(BaseModel):
    """An information page's content."""

    id: str
    content_markdown: str
    attachments: list[Attachment] = []
    url: str = ""


class DocumentText(BaseModel):
    """Extracted text of a document."""

    id: str
    filename: str
    content_type: str
    size_bytes: int
    text: str | None
    truncated: bool = False
    note: str = ""


class SavedFile(BaseModel):
    """A document saved to the local download directory."""

    path: str
    filename: str
    size_bytes: int
    content_type: str


class Overview(BaseModel):
    """What's new: latest messages, news and documents."""

    site: str
    messages: list[MessageSummary]
    news: list[NewsSummary]
    recent_documents: list[RecentDocument]
