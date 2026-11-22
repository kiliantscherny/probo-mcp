import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
import respx
from mcp import Client
from mcp.server.mcpserver import MCPServer

from probo_mcp import archive
from probo_mcp.archive import SEEN_FILE, Candidate, SeenStore
from probo_mcp.client import ProboError
from probo_mcp.config import Settings
from probo_mcp.models import Attachment, MessageSummary, MessageThread, NewsItem, NewsSummary
from probo_mcp.parsers import PROBO_TZ
from probo_mcp.service import ProboService

from .conftest import FILE_ID, MESSAGE_ID, NEWS_ID, OTHER_MESSAGE_ID, SUBFOLDER_FILE_ID

NOW = datetime(2026, 10, 18, tzinfo=PROBO_TZ)


@pytest.fixture
def service(settings: Settings, probo_site: respx.Router) -> ProboService:
    return ProboService.from_settings(settings)


def seen(settings: Settings) -> dict:
    return json.loads((settings.archive_dir / SEEN_FILE).read_text(encoding="utf-8"))["items"]


async def test_first_run_saves_recent_items_and_baselines_older_ones(service: ProboService, settings: Settings) -> None:
    result = await archive.whats_new(service, now=NOW)

    assert result.first_run
    assert result.errors == []
    assert result.remaining == 0
    # Newest first across sections; the May document is outside the 30-day first-run window.
    assert [(i.kind, i.id) for i in result.items] == [
        ("document", FILE_ID),
        ("message", MESSAGE_ID),
        ("news", NEWS_ID),
        ("message", OTHER_MESSAGE_ID),
        ("news", "33333333-4444-5555-6666-777777777777"),
    ]
    assert not any(i.updated for i in result.items)
    assert "1 older or undated item(s) were recorded as history" in result.note
    assert seen(settings)[f"document:{SUBFOLDER_FILE_ID}"]["saved"] is None  # recorded, not fetched

    message = next(i for i in result.items if i.id == MESSAGE_ID)
    folder = Path(message.saved_to)
    assert folder.parent == settings.archive_dir.resolve() / "messages"
    assert folder.name == "2026-10-14 Bike storage keys (2) (11111111)"
    thread_md = (folder / "thread.md").read_text(encoding="utf-8")
    assert thread_md == message.content_markdown
    assert "[floorplan.pdf](<Bilag.pdf>)" in thread_md  # ProBo's link text, saved under the served file name
    assert (folder / "Bilag.pdf").read_bytes().startswith(b"%PDF")
    assert "Hello from the ProBo archive" in (folder / "Bilag.pdf.txt").read_text(encoding="utf-8")
    assert "Hello from the ProBo archive" in message.attachments[0].text_excerpt

    document = result.items[0]
    assert Path(document.saved_to) == settings.archive_dir.resolve() / "documents" / "Budget 2026.pdf"
    assert "Hello from the ProBo archive" in document.content_markdown


async def test_second_run_returns_only_what_changed(service: ProboService, monkeypatch: pytest.MonkeyPatch) -> None:
    first = await archive.whats_new(service, now=NOW)
    again = await archive.whats_new(service, now=NOW)
    assert not again.first_run
    assert again.items == []
    assert again.note == ""

    original = service.list_messages

    async def with_new_reply(*args, **kwargs) -> list[MessageSummary]:
        rows = await original(*args, **kwargs)
        return [
            r.model_copy(update={"subject": "Bike storage keys (3)", "date_text": "17 Oct 2026 - 09:00"})
            if r.id == MESSAGE_ID
            else r
            for r in rows
        ]

    monkeypatch.setattr(service, "list_messages", with_new_reply)
    update = await archive.whats_new(service, now=NOW)
    assert [(i.id, i.updated) for i in update.items] == [(MESSAGE_ID, True)]
    # The update overwrites the same folder rather than starting a new one.
    before = next(i for i in first.items if i.id == MESSAGE_ID)
    assert update.items[0].saved_to == before.saved_to


async def test_reading_in_probo_does_not_hide_items(service: ProboService) -> None:
    """ProBo's read flag is never consulted: only the local seen file decides what is new."""
    await archive.whats_new(service, now=NOW)
    (service.settings.archive_dir / SEEN_FILE).unlink()
    assert len((await archive.whats_new(service, now=NOW)).items) == 5


async def test_max_items_leaves_the_rest_for_the_next_call(service: ProboService) -> None:
    first = await archive.whats_new(service, max_items=2, now=NOW)
    assert (len(first.items), first.remaining) == (2, 3)
    rest = await archive.whats_new(service, max_items=10, now=NOW)
    assert not rest.first_run
    assert (len(rest.items), rest.remaining) == (3, 0)
    assert {i.id for i in first.items}.isdisjoint(i.id for i in rest.items)


async def test_failed_items_stay_new(service: ProboService, monkeypatch: pytest.MonkeyPatch) -> None:
    original = service.get_message

    async def flaky(message_id: str):
        if message_id == OTHER_MESSAGE_ID:
            raise ProboError("Not found")
        return await original(message_id)

    monkeypatch.setattr(service, "get_message", flaky)
    result = await archive.whats_new(service, now=NOW)
    assert len(result.items) == 4
    assert result.errors == ["message 'Indkaldelse til generalforsamling': Not found"]

    monkeypatch.setattr(service, "get_message", original)
    retry = await archive.whats_new(service, now=NOW)
    assert [i.id for i in retry.items] == [OTHER_MESSAGE_ID]


async def test_large_files_are_skipped(settings: Settings, probo_site: respx.Router) -> None:
    service = ProboService.from_settings(replace(settings, confirm_download_mb=0))
    result = await archive.whats_new(service, now=NOW)
    message = next(i for i in result.items if i.id == MESSAGE_ID)
    assert message.attachments[0].saved_to == ""
    assert "Use download_document" in message.attachments[0].note
    assert "Use download_document" in (Path(message.saved_to) / "thread.md").read_text(encoding="utf-8")
    assert not list(Path(message.saved_to).glob("*.pdf"))


async def test_damaged_seen_file_is_an_error(service: ProboService, settings: Settings) -> None:
    settings.archive_dir.mkdir(parents=True)
    (settings.archive_dir / SEEN_FILE).write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="deleting it starts the archive over"):
        await archive.whats_new(service, now=NOW)


def test_entry_names_cannot_escape_the_archive(tmp_path: Path) -> None:
    evil = Candidate("message", MESSAGE_ID, "../../../etc/passwd", "", None, "x")
    folder = archive._entry_dir(tmp_path, "messages", evil, None)
    assert folder.parent == tmp_path.resolve() / "messages"
    with pytest.raises(OSError, match="outside the archive"):
        archive._entry_dir(tmp_path, "messages", evil, "../elsewhere")


def test_seen_store_round_trip(tmp_path: Path) -> None:
    c = Candidate("news", NEWS_ID, "Heating", "", None, "comments=0")
    store = SeenStore(tmp_path).load()
    assert not store.existed
    assert store.is_new(c)
    store.mark(c, "news/x")
    store.save()
    loaded = SeenStore(tmp_path).load()
    assert loaded.existed
    assert not loaded.is_new(c)
    assert loaded.saved(c) == "news/x"
    assert loaded.is_new(replace(c, fingerprint="comments=1"))
    assert not list(tmp_path.glob("*.tmp"))


async def test_whats_new_tool(server: MCPServer, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(archive, "FIRST_RUN_DAYS", 100_000)  # the tool uses the real clock
    async with Client(server) as client:
        result = await client.call_tool("whats_new", {"max_items": 1})
    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["remaining"] >= 1
    assert len(result.structured_content["items"]) == 1
    # RFC 3339 needs an offset: Claude Code rejects the whole result without one.
    date = result.structured_content["items"][0]["date"]
    assert datetime.fromisoformat(date).tzinfo is not None, date
    assert (settings.archive_dir / SEEN_FILE).exists()


async def test_archive_documents_in_messages_are_linked_not_downloaded_again(
    service: ProboService, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = service.get_message
    announced = Attachment(name="Budget", path=f"/member/download_file/document_archive/Member/{FILE_ID}/")

    async def announcing(message_id: str) -> MessageThread:
        thread = await original(message_id)
        cards = [card.model_copy(update={"attachments": [announced]}) for card in thread.messages]
        return thread.model_copy(update={"messages": cards})

    monkeypatch.setattr(service, "get_message", announcing)
    result = await archive.whats_new(service, now=NOW)
    document = next(i for i in result.items if i.kind == "document")
    message = next(i for i in result.items if i.id == MESSAGE_ID)

    assert message.attachments[0].saved_to == document.saved_to
    assert message.attachments[0].note == "Saved with the documents."
    assert "Hello from the ProBo archive" in message.attachments[0].text_excerpt
    assert not list(Path(message.saved_to).glob("*.pdf"))
    assert "[Budget](<../../documents/Budget 2026.pdf>)" in message.content_markdown


async def test_long_recipient_lists_are_shortened(service: ProboService, monkeypatch: pytest.MonkeyPatch) -> None:
    original = service.get_message

    async def to_everyone(message_id: str) -> MessageThread:
        thread = await original(message_id)
        everyone = ", ".join(f"Owner {n}" for n in range(1, 31))
        return thread.model_copy(
            update={"messages": [m.model_copy(update={"recipients": everyone}) for m in thread.messages]}
        )

    monkeypatch.setattr(service, "get_message", to_everyone)
    message = next(i for i in (await archive.whats_new(service, now=NOW)).items if i.id == MESSAGE_ID)
    assert "To: Owner 1, Owner 2," in message.content_markdown
    assert "Owner 10 and 20 more" in message.content_markdown
    assert "Owner 11" not in message.content_markdown


async def test_repeat_last_returns_the_previous_result(service: ProboService) -> None:
    with pytest.raises(ValueError, match="no previous whats_new result"):
        await archive.whats_new(service, repeat_last=True)
    first = await archive.whats_new(service, now=NOW)
    repeated = await archive.whats_new(service, repeat_last=True)
    assert repeated.items == first.items
    assert repeated.note.startswith("Repeated the previous result")
    # Repeating fetches nothing and doesn't touch the seen file: a real call still finds nothing new.
    assert (await archive.whats_new(service, now=NOW)).items == []


# -- history -------------------------------------------------------------------------


async def test_fetch_history_saves_what_the_first_run_only_recorded(service: ProboService, settings: Settings) -> None:
    await archive.whats_new(service, now=NOW)
    history = await archive.fetch_history(service, now=NOW)
    assert [(e.kind, e.id) for e in history.saved] == [("document", SUBFOLDER_FILE_ID)]
    assert history.remaining == 0
    assert Path(history.saved[0].saved_to).is_file()
    assert seen(settings)[f"document:{SUBFOLDER_FILE_ID}"]["saved"]
    # History is never reported as new, and a second pass has nothing left to do.
    assert (await archive.whats_new(service, now=NOW)).items == []
    assert (await archive.fetch_history(service, now=NOW)).saved == []


async def test_fetch_history_first_leaves_recent_items_for_whats_new(service: ProboService) -> None:
    history = await archive.fetch_history(service, sections=["news", "document", "message"], now=NOW)
    assert [e.id for e in history.saved] == [SUBFOLDER_FILE_ID]  # the only item older than 30 days
    new = await archive.whats_new(service, now=NOW)
    assert not new.first_run
    assert len(new.items) == 5
    assert SUBFOLDER_FILE_ID not in {i.id for i in new.items}


async def test_fetch_history_leaves_changes_to_whats_new(
    service: ProboService, monkeypatch: pytest.MonkeyPatch
) -> None:
    await archive.whats_new(service, now=NOW)
    original = service.find_documents

    async def reuploaded(**kwargs):
        result = await original(**kwargs)
        docs = [
            d.model_copy(update={"date_text": "1 Jan 2020"}) if d.id == SUBFOLDER_FILE_ID else d
            for d in result.documents
        ]
        return result.model_copy(update={"documents": docs})

    monkeypatch.setattr(service, "find_documents", reuploaded)
    assert (await archive.fetch_history(service, now=NOW)).saved == []
    assert [i.id for i in (await archive.whats_new(service, now=NOW)).items] == [SUBFOLDER_FILE_ID]


async def test_fetch_history_reads_every_page(service: ProboService, monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {
        p: [
            NewsSummary(id=f"{p:08d}-0000-0000-0000-{n:012d}", subject=f"Old post {p}.{n}", date_text="1.1.2020",
                        date=datetime(2020, 1, 1, tzinfo=PROBO_TZ))
            for n in range(3)
        ]
        for p in range(1, archive.MAX_PAGES + 4)
    }  # fmt: skip

    async def list_news(search=None, page: int = 1):
        return pages.get(page, [])

    async def get_news(news_id: str) -> NewsItem:
        return NewsItem(id=news_id, title="Old post", content_markdown="Text")

    monkeypatch.setattr(service, "list_news", list_news)
    monkeypatch.setattr(service, "get_news", get_news)
    history = await archive.fetch_history(service, sections=["news"], max_items=10, now=NOW)
    assert (len(history.saved), history.remaining) == (10, 3 * len(pages) - 10)
    rest = await archive.fetch_history(service, sections=["news"], max_items=100, now=NOW)
    assert (len(rest.saved), rest.remaining) == (3 * len(pages) - 10, 0)


async def test_archived_message_folders_are_checked(service: ProboService, monkeypatch: pytest.MonkeyPatch) -> None:
    folders: list[str] = []
    original = service.list_messages

    async def spy(folder="inbox", search=None, page: int = 1):
        folders.append(folder)
        return await original(folder, search, page)

    monkeypatch.setattr(service, "list_messages", spy)
    await archive.whats_new(service, now=NOW)
    assert {"inbox", "archive", "archived_notifications"} <= set(folders)


async def test_undated_items_are_new_after_the_first_run(
    service: ProboService, monkeypatch: pytest.MonkeyPatch
) -> None:
    await archive.whats_new(service, now=NOW)
    original = service.list_news

    async def with_undated(search=None, page: int = 1):
        rows = await original(search, page)
        return [*rows, NewsSummary(id="cccccccc-0000-0000-0000-000000000000", subject="No date", date_text="?")]

    async def get_news(news_id: str) -> NewsItem:
        return NewsItem(id=news_id, title="No date", content_markdown="Text")

    monkeypatch.setattr(service, "list_news", with_undated)
    monkeypatch.setattr(service, "get_news", get_news)
    assert [i.title for i in (await archive.whats_new(service, now=NOW)).items] == ["No date"]


def test_history_line_is_derived_for_older_seen_files(tmp_path: Path) -> None:
    (tmp_path / SEEN_FILE).write_text(
        json.dumps(
            {"version": 1, "items": {"news:x": {"fingerprint": "", "saved": None, "seen_at": "2026-11-18T22:00:00"}}}
        ),
        encoding="utf-8",
    )
    store = SeenStore(tmp_path).load()
    assert store.since == datetime(2026, 10, 19, 22, tzinfo=PROBO_TZ)
