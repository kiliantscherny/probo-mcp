"""whats_new: fetch what the local archive hasn't seen yet, save it, and remember it.

"New" is tracked here, never by ProBo's read/unread flag: a thread already read in the
browser or the app is still new until this archive has saved it. A thread with a new
reply, or a news post with a new comment, counts as new again (``updated``).

Everything is saved under ``Settings.archive_dir``::

    messages/2026-10-01 Indkaldelse til generalforsamling (aaaaaaaa)/thread.md (+ attachments)
    news/2026-10-13 Heating off tomorrow (22222222)/post.md (+ attachments)
    documents/<archive folder>/<file> (+ <file>.txt with the extracted text)
    .probo-mcp-seen.json       what has been saved, so the next call only returns what changed
    .probo-mcp-last-run.json   the last result, so a reply lost on the way can be asked for again

Archive documents attached to a message (ProBo's "Nyt dokument" notifications) are linked to
their copy under ``documents/`` rather than downloaded twice.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import anyio.to_thread
import httpx

from .client import UUID, FileTooLargeError, ProboError
from .models import Attachment, HistoryEntry, HistoryResult, NewItem, SavedAttachment, WhatsNew
from .parsers import OLDEST, PROBO_TZ
from .service import MessageFolder, ProboService, ProgressCallback, _write_file, extract_text, safe_filename

logger = logging.getLogger(__name__)

SEEN_FILE = ".probo-mcp-seen.json"
LAST_RUN_FILE = ".probo-mcp-last-run.json"
#: On the first run, only items from this many days back count as new; older ones are just recorded.
FIRST_RUN_DAYS = 30
#: List pages to read per section before giving up on finding already-archived items.
MAX_PAGES = 5
EXCERPT_CHARS = 2_000
#: Recipients listed per message before "and N more" (association-wide mail goes to everyone).
MAX_RECIPIENTS = 10
_ARCHIVE_DOCUMENT = re.compile(rf"/download_file/document_archive/\w+/({UUID})/$")

Kind = Literal["message", "news", "document"]
_RETRYABLE = (ProboError, httpx.HTTPError, OSError)


@dataclass(frozen=True)
class Candidate:
    """A list row that may be new."""

    kind: Kind
    id: str
    title: str
    date_text: str
    date: datetime | None
    fingerprint: str  # changes when the item changes (new reply, new comment, new upload)
    url: str = ""
    folder: str = ""  # archive folder path, documents only

    @property
    def key(self) -> str:
        """Key in the seen file."""
        return f"{self.kind}:{self.id}"


class SeenStore:
    """What the archive holds: ``{"<kind>:<id>": {"fingerprint", "saved", "seen_at"}}``.

    ``since`` is the history line, set on the first run: items dated before it are history (recorded,
    and saved by `fetch_history`); anything after it, or any change to a known item, is new.
    """

    def __init__(self, root: Path):
        """Point at the seen file in ``root``; call `load` to read it."""
        self.path = root / SEEN_FILE
        self.items: dict[str, dict[str, str | None]] = {}
        self.since: datetime | None = None
        self.existed = False

    def load(self) -> SeenStore:
        """Read the seen file if there is one. A damaged file is an error, not a silent restart."""
        if not self.path.exists():
            return self
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            items = data["items"]
            if not isinstance(items, dict):
                raise TypeError("'items' is not an object")
            since = data.get("since")
            self.since = _aware(datetime.fromisoformat(since)) if since else _since_from(items)
        except (ValueError, KeyError, TypeError) as e:
            raise ValueError(
                f"Could not read {self.path} ({e}). Fix or delete it; deleting it starts the archive over."
            ) from e
        self.items = items
        self.existed = True
        return self

    def is_new(self, c: Candidate) -> bool:
        """Never recorded, or changed since it was."""
        entry = self.items.get(c.key)
        return entry is None or entry.get("fingerprint") != c.fingerprint

    def was_seen(self, c: Candidate) -> bool:
        """Recorded at least once before."""
        return c.key in self.items

    def is_history(self, c: Candidate) -> bool:
        """Dated before the history line: old news, not something new. Undated items never are."""
        return c.date is not None and self.since is not None and c.date < self.since

    def saved(self, c: Candidate) -> str | None:
        """Where the item was saved, relative to the archive root."""
        return (self.items.get(c.key) or {}).get("saved")

    def mark(self, c: Candidate, saved: str | None) -> None:
        """Record ``c`` (``saved`` is None for history that hasn't been fetched yet)."""
        self.items[c.key] = {
            "fingerprint": c.fingerprint,
            "saved": saved,
            "seen_at": datetime.now(PROBO_TZ).isoformat(timespec="seconds"),
        }

    def save(self) -> None:
        """Write the seen file atomically, so a crash never leaves it half-written."""
        data = {"version": 1, "since": self.since.isoformat() if self.since else None, "items": self.items}
        _write_file(self.path, json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=PROBO_TZ)


def _since_from(items: dict) -> datetime | None:
    """History line for seen files written before it existed: the first run minus the first-run window."""
    times = [_aware(datetime.fromisoformat(v["seen_at"])) for v in items.values() if v.get("seen_at")]
    return min(times) - timedelta(days=FIRST_RUN_DAYS) if times else None


# -- collecting candidates ---------------------------------------------------------

Fetch = Callable[[int], Awaitable[Sequence[Candidate]]]
#: Message folders to look in: the inbox, plus threads and notifications archived in the browser.
MESSAGE_FOLDERS = ("inbox", "archive", "archived_notifications")
#: Safety stop when reading every page of a list for fetch_history.
MAX_HISTORY_PAGES = 500


async def _paged(fetch: Fetch, store: SeenStore | None, max_pages: int = MAX_PAGES) -> list[Candidate]:
    """Read list pages (newest first), stopping early once a page holds nothing new or only history.

    With ``store=None``, read every page (up to ``max_pages``).
    """
    out: list[Candidate] = []
    ids: set[str] = set()
    for page in range(1, max_pages + 1):
        rows = [c for c in await fetch(page) if c.id not in ids]
        if not rows:  # past the last page (or ProBo repeating it)
            break
        ids.update(c.id for c in rows)
        out.extend(rows)
        if store is not None and (
            not any(store.is_new(c) for c in rows) or all(c.date is not None and store.is_history(c) for c in rows)
        ):
            break
    return out


def _message_fetch(service: ProboService, folder: MessageFolder) -> Fetch:
    async def fetch(page: int) -> list[Candidate]:
        return [
            # The subject carries the reply count ("Keys (2)") and the date is the latest activity.
            Candidate("message", m.id, m.subject, m.date_text, m.date, f"{m.subject}|{m.date_text}", m.url)
            for m in await service.list_messages(folder, page=page)
        ]

    return fetch


def _news_fetch(service: ProboService) -> Fetch:
    async def fetch(page: int) -> list[Candidate]:
        return [
            Candidate("news", n.id, n.subject, n.date_text, n.date, f"comments={n.comments}", n.url)
            for n in await service.list_news(page=page)
        ]

    return fetch


async def _documents(service: ProboService, progress: ProgressCallback | None) -> tuple[list[Candidate], str]:
    docs = await service.find_documents(progress=progress)
    found = [
        Candidate(
            "document",
            d.id,
            d.name,
            d.added_text or d.date_text,
            d.added,
            f"{d.date_text}|{d.added_text}",
            d.url,
            d.folder,
        )
        for d in docs.documents
    ]
    return found, docs.note


def _unique(candidates: list[Candidate]) -> list[Candidate]:
    """One candidate per item (a thread can show up in more than one folder)."""
    return list({c.key: c for c in reversed(candidates)}.values())[::-1]


async def collect(
    service: ProboService,
    store: SeenStore | None,
    progress: ProgressCallback | None,
    sections: Sequence[Kind] = ("message", "news", "document"),
) -> tuple[list[Candidate], str]:
    """Every item that could be new (``store``), or every item there is (``store=None``), plus a note."""
    pages = MAX_PAGES if store is not None else MAX_HISTORY_PAGES
    found: list[Candidate] = []
    note = ""
    if "message" in sections:
        for folder in MESSAGE_FOLDERS:
            found += await _paged(_message_fetch(service, folder), store, pages)
    if "news" in sections:
        found += await _paged(_news_fetch(service), store, pages)
    if "document" in sections:
        documents, note = await _documents(service, progress)
        found += documents
    return _unique(found), note


# -- saving ------------------------------------------------------------------------


def _inside(root: Path, path: Path) -> Path:
    """Resolve ``path`` and make sure it stays under ``root``."""
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise OSError(f"Refusing to write outside the archive: {resolved}")
    return resolved


def _entry_dir(root: Path, section: str, c: Candidate, saved: str | None) -> Path:
    """The item's folder: reused when updating, so a new reply lands next to the old ones."""
    if saved:
        return _inside(root, root / saved)
    day = c.date.strftime("%Y-%m-%d") if c.date else "undated"
    return _inside(root, root / section / safe_filename(f"{day} {c.title[:80]} ({c.id[:8]})"))


async def _write(path: Path, content: bytes | str, *, downloaded: bool = False) -> None:
    data = content.encode("utf-8") if isinstance(content, str) else content
    await anyio.to_thread.run_sync(_write_file, path, data, downloaded)


async def _save_file(service: ProboService, root: Path, folder: Path, att: Attachment) -> SavedAttachment:
    """Download one file into ``folder`` and save its text next to it, skipping very large files."""
    limit_mb = service.settings.confirm_download_mb
    info = await service.file_info(att.path)
    if info.size_bytes is not None and info.size_bytes > limit_mb * 1024 * 1024:
        size = info.size_bytes / 1024 / 1024
        return SavedAttachment(
            name=att.name, path=att.path, note=f"Skipped: {size:.0f} MB is over {limit_mb} MB. Use download_document."
        )
    try:
        f = await service.download(att.path, max_mb=limit_mb)  # also caps files that didn't say their size
    except FileTooLargeError:
        return SavedAttachment(
            name=att.name, path=att.path, note=f"Skipped: over {limit_mb} MB. Use download_document."
        )
    target = _inside(root, folder / safe_filename(f.filename or att.name))
    await _write(target, f.content, downloaded=True)
    text, note = await anyio.to_thread.run_sync(extract_text, f)  # PDF parsing is CPU-bound
    if text:
        await _write(target.with_name(target.name + ".txt"), text)
    return SavedAttachment(
        name=att.name, path=att.path, saved_to=str(target), text_excerpt=(text or "")[:EXCERPT_CHARS], note=note
    )


def _existing_text(target: Path) -> str | None:
    """Start of the text saved next to ``target`` ('' if none), or None when ``target`` is missing."""
    if not target.is_file():
        return None
    text_file = target.with_name(target.name + ".txt")
    return text_file.read_text(encoding="utf-8")[:EXCERPT_CHARS] if text_file.is_file() else ""


async def _archived_copy(root: Path, store: SeenStore, att: Attachment) -> SavedAttachment | None:
    """The copy under ``documents/`` of an attached archive document, if it has been saved already."""
    m = _ARCHIVE_DOCUMENT.search(att.path)
    saved = (store.items.get(f"document:{m.group(1).lower()}") or {}).get("saved") if m else None
    if not saved:
        return None
    target = _inside(root, root / saved)
    excerpt = await anyio.to_thread.run_sync(_existing_text, target)
    if excerpt is None:  # deleted by hand: download it again
        return None
    return SavedAttachment(
        name=att.name, path=att.path, saved_to=str(target), text_excerpt=excerpt, note="Saved with the documents."
    )


async def _save_attachment(
    service: ProboService, root: Path, store: SeenStore, folder: Path, att: Attachment
) -> SavedAttachment:
    return await _archived_copy(root, store, att) or await _save_file(service, root, folder, att)


def _attachment_lines(saved: list[SavedAttachment], folder: Path) -> str:
    if not saved:
        return ""
    lines = [
        f"- [{a.name}](<{Path(a.saved_to).relative_to(folder, walk_up=True).as_posix()}>)"
        if a.saved_to
        else f"- {a.name} ({a.note})"
        for a in saved
    ]
    return "\n\n## Attachments\n\n" + "\n".join(lines) + "\n"


def _recipients(text: str) -> str:
    names = [n.strip() for n in text.split(",") if n.strip()]
    if len(names) <= MAX_RECIPIENTS:
        return ", ".join(names)
    return ", ".join(names[:MAX_RECIPIENTS]) + f" and {len(names) - MAX_RECIPIENTS} more"


async def _save_message(
    service: ProboService, root: Path, store: SeenStore, c: Candidate
) -> tuple[Path, str, list[SavedAttachment]]:
    thread = await service.get_message(c.id)
    folder = _entry_dir(root, "messages", c, store.saved(c))
    unique = {a.path: a for card in thread.messages for a in card.attachments}
    attachments = [await _save_attachment(service, root, store, folder, a) for a in unique.values()]
    parts = [f"# {thread.subject or c.title}\n\n[Open in ProBo]({thread.url})"]
    for card in thread.messages:
        to = f"\n\nTo: {_recipients(card.recipients)}" if card.recipients else ""
        parts.append(f"## {card.sender} · {card.date_text}{to}\n\n{card.body_markdown}")
    markdown = "\n\n".join(parts) + "\n" + _attachment_lines(attachments, folder)
    await _write(folder / "thread.md", markdown)
    return folder, markdown, attachments


async def _save_news(
    service: ProboService, root: Path, store: SeenStore, c: Candidate
) -> tuple[Path, str, list[SavedAttachment]]:
    post = await service.get_news(c.id)
    folder = _entry_dir(root, "news", c, store.saved(c))
    attachments = [await _save_attachment(service, root, store, folder, a) for a in post.attachments]
    markdown = (
        f"# {post.title or c.title}\n\n{post.date_text} · [Open in ProBo]({post.url})\n\n{post.content_markdown}\n"
    )
    if post.comments_markdown:
        markdown += f"\n## Comments\n\n{post.comments_markdown}\n"
    markdown += _attachment_lines(attachments, folder)
    await _write(folder / "post.md", markdown)
    return folder, markdown, attachments


async def _save_document(service: ProboService, root: Path, c: Candidate) -> tuple[Path, str, list[SavedAttachment]]:
    folder = _inside(root, root.joinpath("documents", *(safe_filename(p) for p in c.folder.split("/") if p)))
    saved = await _save_file(service, root, folder, Attachment(name=c.title, path=c.id))
    path = Path(saved.saved_to) if saved.saved_to else folder
    return path, saved.text_excerpt or saved.note, []


async def save_item(service: ProboService, root: Path, store: SeenStore, c: Candidate) -> NewItem:
    """Fetch ``c`` in full, save it under ``root`` and return what was saved."""
    if c.kind == "message":
        path, markdown, attachments = await _save_message(service, root, store, c)
    elif c.kind == "news":
        path, markdown, attachments = await _save_news(service, root, store, c)
    else:
        path, markdown, attachments = await _save_document(service, root, c)
    return NewItem(
        kind=c.kind,
        id=c.id,
        title=c.title,
        date_text=c.date_text,
        date=c.date,
        updated=store.was_seen(c),
        url=c.url,
        saved_to=str(path),
        content_markdown=markdown,
        attachments=attachments,
    )


# -- the whole run -----------------------------------------------------------------


async def whats_new(
    service: ProboService,
    *,
    max_items: int = 15,
    repeat_last: bool = False,
    progress: ProgressCallback | None = None,
    now: datetime | None = None,
) -> WhatsNew:
    """Fetch, save and remember everything the archive hasn't seen, newest first.

    With ``repeat_last``, return the previous result again without fetching anything: items are
    remembered as soon as they are saved, so a reply lost on the way would otherwise be skipped.
    """
    root = service.settings.archive_dir
    if repeat_last:
        return await anyio.to_thread.run_sync(_last_run, root)
    async with service.archive_lock:  # two overlapping calls would fetch and record the same items
        store = SeenStore(root).load()
        first_run = not store.existed
        if store.since is None:  # first run: only the last FIRST_RUN_DAYS count as new
            store.since = (now or datetime.now(PROBO_TZ)) - timedelta(days=FIRST_RUN_DAYS)
        found, note = await collect(service, store, progress)

        new: list[Candidate] = []
        baselined = 0
        for c in found:
            if not store.is_new(c):
                continue
            # Undated items count as history only on the first run; after that, an unknown item is new.
            if not store.was_seen(c) and (store.is_history(c) or (first_run and c.date is None)):
                store.mark(c, None)  # old: remember it as history (fetch_history saves it) without reporting
                baselined += 1
            else:
                new.append(c)
        new.sort(key=lambda c: c.date or OLDEST, reverse=True)
        batch = new[:max_items]
        store.save()

        items: list[NewItem] = []
        errors: list[str] = []
        # Documents first, so messages announcing them can link to the copy instead of downloading it again.
        for i, c in enumerate(sorted(batch, key=lambda c: c.kind != "document"), 1):
            try:
                item = await save_item(service, root, store, c)
            except _RETRYABLE as e:
                logger.warning("whats_new: could not save %s %s: %s", c.kind, c.id, e)
                errors.append(f"{c.kind} {c.title!r}: {e}")
                continue
            store.mark(c, Path(item.saved_to).relative_to(root.resolve()).as_posix())
            store.save()  # after every item, so an interrupted run keeps what it already saved
            items.append(item)
            if progress is not None:
                await progress(i, len(batch), f"Saved {c.title}")

        items.sort(key=lambda item: item.date or OLDEST, reverse=True)
        notes = [note] if note else []
        if baselined:
            notes.append(
                f"{baselined} older or undated item(s) were recorded as history without being fetched; "
                "fetch_history saves them to the archive."
            )
        result = WhatsNew(
            items=items,
            archive_dir=str(root),
            first_run=first_run,
            remaining=len(new) - len(batch),
            errors=errors,
            note=" ".join(notes),
        )
        await _write(root / LAST_RUN_FILE, result.model_dump_json(indent=2))
    return result


def _last_run(root: Path) -> WhatsNew:
    path = root / LAST_RUN_FILE
    if not path.is_file():
        raise ValueError("There is no previous whats_new result to repeat yet.")
    last = WhatsNew.model_validate_json(path.read_text(encoding="utf-8"))
    note = "Repeated the previous result; nothing was fetched." + (f" {last.note}" if last.note else "")
    return last.model_copy(update={"note": note})


# -- history -----------------------------------------------------------------------


async def fetch_history(
    service: ProboService,
    *,
    sections: Sequence[Kind] = ("news", "document"),
    max_items: int = 50,
    progress: ProgressCallback | None = None,
    now: datetime | None = None,
) -> HistoryResult:
    """Save older items (before the history line) that aren't in the archive yet, newest first.

    Reads every page of the chosen lists. Never touches what whats_new reports: new items, and
    changes to known ones, are left for it.
    """
    root = service.settings.archive_dir
    async with service.archive_lock:
        store = SeenStore(root).load()
        if store.since is None:  # history before any whats_new run: draw the line now
            store.since = (now or datetime.now(PROBO_TZ)) - timedelta(days=FIRST_RUN_DAYS)
        found, note = await collect(service, None, progress, sections)
        pending = [
            c
            for c in found
            if store.saved(c) is None
            # An unknown undated item may be new: leave it to whats_new, like changes to known items.
            and (store.is_history(c) or (c.date is None and store.was_seen(c)))
            and not (store.was_seen(c) and store.is_new(c))
        ]
        pending.sort(key=lambda c: c.date or OLDEST, reverse=True)
        batch = pending[:max_items]
        store.save()

        saved: list[HistoryEntry] = []
        errors: list[str] = []
        for i, c in enumerate(sorted(batch, key=lambda c: c.kind != "document"), 1):
            try:
                item = await save_item(service, root, store, c)
            except _RETRYABLE as e:
                logger.warning("fetch_history: could not save %s %s: %s", c.kind, c.id, e)
                errors.append(f"{c.kind} {c.title!r}: {e}")
                continue
            store.mark(c, Path(item.saved_to).relative_to(root.resolve()).as_posix())
            store.save()
            saved.append(
                HistoryEntry(kind=c.kind, id=c.id, title=c.title, date_text=c.date_text, saved_to=item.saved_to)
            )
            if progress is not None:
                await progress(i, len(batch), f"Saved {c.title}")

    return HistoryResult(
        saved=saved, archive_dir=str(root), remaining=len(pending) - len(batch), errors=errors, note=note
    )
