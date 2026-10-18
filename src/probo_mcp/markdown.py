"""Render models as Markdown documents (for resources and prompt context)."""

from __future__ import annotations

from .models import Attachment, DocumentText, InfoPage, MessageThread, NewsItem


def _attachments(items: list[Attachment]) -> str:
    if not items:
        return ""
    lines = "\n".join(f"- {a.name} (`{a.path}`)" for a in items)
    return f"\n\n**Attachments**\n\n{lines}"


def thread_markdown(thread: MessageThread) -> str:
    """A message thread as one Markdown document."""
    parts = [f"# {thread.subject}", f"<{thread.url}>" if thread.url else ""]
    for card in thread.messages:
        header = f"## {card.sender} · {card.date_text}"
        to = f"\n\n_To: {card.recipients}_" if card.recipients else ""
        parts.append(f"{header}{to}\n\n{card.body_markdown}{_attachments(card.attachments)}")
    return "\n\n".join(p for p in parts if p)


def news_markdown(item: NewsItem) -> str:
    """A news post (and its comments) as Markdown."""
    parts = [f"# {item.title or 'News'}", f"_{item.date_text}_" if item.date_text else "", item.content_markdown]
    if item.attachments:
        parts.append(_attachments(item.attachments).strip())
    if item.comments_markdown:
        parts.append(f"## Comments\n\n{item.comments_markdown}")
    if item.url:
        parts.append(f"<{item.url}>")
    return "\n\n".join(p for p in parts if p)


def document_markdown(doc: DocumentText) -> str:
    """Document metadata plus extracted text."""
    meta = f"_{doc.content_type}, {doc.size_bytes / 1024:.0f} KB_"
    note = f"\n\n> {doc.note}" if doc.note else ""
    body = f"\n\n{doc.text}" if doc.text else ""
    return f"# {doc.filename}\n\n{meta}{note}{body}"


def info_page_markdown(page: InfoPage) -> str:
    """An information page as Markdown."""
    link = f"\n\n<{page.url}>" if page.url else ""
    return f"{page.content_markdown}{_attachments(page.attachments)}{link}"
