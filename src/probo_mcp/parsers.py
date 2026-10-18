"""Pure HTML -> model parsers for ProBo pages (no network I/O here).

Selectors mirror ProBo's markup: the "v3" message UI (``.v3-message-row``,
``.v3-message-card``), Django-admin changelists (``td.field-<name>``) for news,
and ``.document-item__link`` rows in the document archive.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

from markdownify import markdownify
from selectolax.lexbor import LexborHTMLParser, LexborNode

from .client import UUID
from .models import (
    Attachment,
    DocumentEntry,
    DocumentFolder,
    InfoPage,
    InfoPageLink,
    MessageCard,
    MessageSummary,
    MessageThread,
    NewsItem,
    NewsSummary,
    RecentDocument,
)

_UUID_IN = re.compile(UUID)
_DOWNLOAD_HINT = re.compile(r"/(download_file|download_file_landing|media)/")

# Page chrome that should never end up in extracted content.
# Note: not `form` - Django-admin pages wrap the real content in a <form>.
_NOISE = (
    "script, style, svg, button, input, textarea, select, snack-bar, page-help, changeform-toolbar, "
    ".object-tools, .close-button, .mobile-label, .u-hide, .js-inline-admin-formset, "
    ".section-comment-form, .comment-create"
)


def parse_probo_date(text: str) -> datetime | None:
    """Parse the date strings ProBo shows in lists and threads.

    ProBo mixes formats depending on page and UI language, e.g.:
        "14 Oct 2026 - 18:22", "30 Sept 2026 · 19:15", "15 Okt 2026",
        "13 Maj 2026", "14.10.2026", "13. oktober 2026 12:01"
    Return a naive datetime (midnight when there is no time), or None when the
    text can't be parsed. Never raise: callers always keep the raw text too.
    """
    # TODO(you): implement - see tests/test_dates.py for the expected results.
    return None


# -- helpers -----------------------------------------------------------------


def _text(node: LexborNode | None) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.text(deep=True, separator=" ")).strip()


def _uuid(value: str | None) -> str | None:
    m = _UUID_IN.search(value or "")
    return m.group(0).lower() if m else None


def _path(href: str) -> str:
    return urlparse(href).path


def html_to_markdown(node: LexborNode | None) -> str:
    """Convert a node to Markdown, dropping page chrome (buttons, forms, toolbars...)."""
    if node is None:
        return ""
    for junk in node.css(_NOISE):
        junk.decompose()
    md = markdownify(node.html or "", heading_style="ATX", strip=["img"])
    return re.sub(r"\n{3,}", "\n\n", md).strip()


def _attachments(node: LexborNode | None) -> list[Attachment]:
    if node is None:
        return []
    seen: dict[str, Attachment] = {}
    for a in node.css("a[href]"):
        href = a.attributes.get("href") or ""
        if _DOWNLOAD_HINT.search(href) and "export_message_pdf" not in href:
            path = _path(href).replace("/download_file_landing/", "/download_file/")
            seen.setdefault(path, Attachment(name=_text(a) or path.rsplit("/", 2)[-2], path=path))
    return list(seen.values())


def _lines(node: LexborNode) -> list[str]:
    raw = node.text(deep=True, separator="\n")
    return [ln.strip() for ln in raw.splitlines() if ln.strip()]


# -- messages ----------------------------------------------------------------


def parse_message_list(html: str) -> list[MessageSummary]:
    """Parse the rows of a message folder (HTMX partial)."""
    tree = LexborHTMLParser(html)
    out: list[MessageSummary] = []
    for row in tree.css(".v3-message-row"):
        link = row.css_first("a.v3-message-row__body") or row.css_first("a[href*='/communication/message/']")
        msg_id = _uuid(link.attributes.get("href") if link else None)
        if not msg_id:
            continue
        date_text = _text(row.css_first(".v3-message-row__date"))
        out.append(
            MessageSummary(
                id=msg_id,
                sender=_text(row.css_first(".v3-message-row__sender")),
                subject=_text(row.css_first(".v3-message-row__subject")),
                date_text=date_text,
                date=parse_probo_date(date_text),
            )
        )
    return out


def parse_message_thread(html: str, message_id: str) -> MessageThread:
    """Parse a message thread page into one card per message."""
    tree = LexborHTMLParser(html)
    cards: list[MessageCard] = []
    for card in tree.css(".v3-message-card"):
        date_text = _text(card.css_first(".v3-message-card__date"))
        content = card.css_first(".v3-message-card__content") or card.css_first(".v3-message-card__body")
        cards.append(
            MessageCard(
                sender=_text(card.css_first(".v3-message-card__sender-name")),
                date_text=date_text,
                date=parse_probo_date(date_text),
                recipients=_text(card.css_first(".v3-message-card__recipients-list")),
                attachments=_attachments(card),
                body_markdown=html_to_markdown(content),
            )
        )
    return MessageThread(id=message_id, subject=_text(tree.css_first(".v3-thread__subject")), messages=cards)


# -- news --------------------------------------------------------------------


def parse_news_list(html: str) -> list[NewsSummary]:
    """Parse news changelist rows (HTMX partial of ``<tr>`` elements)."""
    # HTMX partials are bare <tr> rows; wrap them so the parser keeps the table structure.
    tree = LexborHTMLParser(html if "<table" in html else f"<table>{html}</table>")
    for label in tree.css(".mobile-label"):  # e.g. "Overskrift", "Oprettet" shown on small screens
        label.decompose()
    out: list[NewsSummary] = []
    for row in tree.css("tr"):
        link = row.css_first("a[href*='/communication/news/']")
        news_id = _uuid(link.attributes.get("href") if link else None)
        if not news_id:
            continue
        date_text = _text(row.css_first("td.field-created_date"))
        out.append(
            NewsSummary(
                id=news_id,
                subject=_text(row.css_first(".field-subject")),
                date_text=date_text,
                date=parse_probo_date(date_text),
                comments=_text(row.css_first(".field-news_comments")),
            )
        )
    return out


def _main(tree: LexborHTMLParser) -> LexborNode | None:
    return tree.css_first("main-content") or tree.css_first("main") or tree.body


def parse_news_item(html: str, news_id: str) -> NewsItem:
    """Parse a news post, rendered by ProBo as a read-only Django-admin change form."""
    tree = LexborHTMLParser(html)
    main = _main(tree)
    # The post is rendered as a read-only Django-admin change form.
    body = tree.css_first(".fieldsets") or main
    header = body.css_first(".fieldset") if body else None
    title = _text(header.css_first("h3")) if header else ""
    date_text = _text(header.css_first("small")) if header else ""
    if header is not None and (title or date_text):
        header.decompose()
    for label in body.css(".control-group > label") if body else []:  # "Tekst"
        label.decompose()
    comments = tree.css_first(".comment-list")
    return NewsItem(
        id=news_id,
        title=title,
        date_text=date_text,
        date=parse_probo_date(date_text),
        attachments=_attachments(body),
        content_markdown=html_to_markdown(body),
        comments_markdown=html_to_markdown(comments),
    )


# -- document archive --------------------------------------------------------


def parse_document_folder(html: str, folder_id: str | None) -> DocumentFolder:
    """Parse one document-archive folder: breadcrumb path, sub-folders and files."""
    tree = LexborHTMLParser(html)
    entries: list[DocumentEntry] = []
    # Subfolders start with a "Tilbage" (back) entry pointing at the parent; skip
    # anything that points at the current folder or one of its breadcrumb ancestors.
    ancestors = {
        _uuid((a.attributes.get("href") or "") + (a.attributes.get("hx-get") or ""))
        for a in tree.css("a.folder-path-link")
    }
    seen: set[str] = {i for i in ancestors | {folder_id} if i}
    for link in tree.css("a.document-item__link"):
        target = (link.attributes.get("href") or "") + " " + (link.attributes.get("hx-get") or "")
        entry_id = _uuid(target)
        if not entry_id or entry_id in seen:
            continue
        seen.add(entry_id)
        if "download_file" in target:
            kind = "file"
        elif "/document_archive/member/" in target:
            kind = "folder"
        else:
            continue
        name, *dates = _lines(link) or [""]
        date_text = dates[0] if dates else ""
        entries.append(
            DocumentEntry(
                kind=kind,
                id=entry_id,
                name=name,
                date_text=date_text,
                date=parse_probo_date(date_text),
                added_text=dates[1] if len(dates) > 1 else "",
            )
        )
    path = [_text(a) for a in tree.css("a.folder-path-link") if _text(a)]
    return DocumentFolder(folder_id=folder_id, path=path, entries=entries)


def parse_recent_documents(html: str) -> list[RecentDocument]:
    """Parse the archive's "Seneste tilføjede dokumenter" (recently added) widget."""
    tree = LexborHTMLParser(html)
    out: list[RecentDocument] = []
    seen: set[str] = set()
    for link in tree.css("a.document-recent-item"):
        doc_id = _uuid((link.attributes.get("href") or "") + (link.attributes.get("hx-get") or ""))
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        date_text = _text(link.css_first(".document-recent-item__date"))
        folder = _text(link.css_first(".document-recent-item__path"))
        # The file name isn't wrapped in its own class; it's whatever text remains.
        name = next((ln for ln in _lines(link) if ln not in (date_text, folder)), "")
        out.append(
            RecentDocument(id=doc_id, name=name, folder=folder, date_text=date_text, date=parse_probo_date(date_text))
        )
    return out


# -- info pages --------------------------------------------------------------


def parse_info_page_links(html: str) -> list[InfoPageLink]:
    """Collect the info-page links from the navigation menu."""
    tree = LexborHTMLParser(html)
    out: dict[str, InfoPageLink] = {}
    for a in tree.css("a[href*='/member/communities/page/']"):
        page_id = _uuid(a.attributes.get("href"))
        title = _text(a)
        if page_id and title and page_id not in out:
            out[page_id] = InfoPageLink(id=page_id, title=title)
    return list(out.values())


def parse_info_page(html: str, page_id: str) -> InfoPage:
    """Parse an information page's content."""
    tree = LexborHTMLParser(html)
    node = tree.css_first(".info-page-content") or _main(tree)
    return InfoPage(id=page_id, attachments=_attachments(node), content_markdown=html_to_markdown(node))
