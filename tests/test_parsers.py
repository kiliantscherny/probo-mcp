from pathlib import Path

from probo_mcp import parsers

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_message_list():
    msgs = parsers.parse_message_list(load("message_list.html"))
    assert [m.id for m in msgs] == ["11111111-2222-3333-4444-555555555555", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"]
    assert msgs[0].sender == "Jane Resident"
    assert msgs[0].subject == "Bike storage keys (2)"
    assert msgs[0].date_text == "14 Oct 2026 - 18:22"


def test_message_thread():
    thread = parsers.parse_message_thread(load("message_thread.html"), "11111111-2222-3333-4444-555555555555")
    assert thread.subject == "Bike storage keys"
    assert len(thread.messages) == 2
    first = thread.messages[0]
    assert first.sender == "Jane Resident"
    assert first.recipients == "Bestyrelsesmedlemmer"
    assert "Where can I get a **key**?" in first.body_markdown
    assert "Vis mere" not in first.body_markdown
    # Attachments are normalised to the direct download route; the PDF export and
    # state-changing toggle_subscription link are never treated as attachments.
    assert [a.path for a in first.attachments] == [
        "/member/download_file/message/Attachment/99999999-8888-7777-6666-555555555555/"
    ]
    assert thread.messages[1].body_markdown == "Ask the caretaker."


def test_news_list():
    news = parsers.parse_news_list(load("news_rows.html"))
    assert [n.subject for n in news] == ["Heating off tomorrow", "Keypad on the street door"]
    assert news[0].id == "22222222-3333-4444-5555-666666666666"
    assert news[0].date_text == "13. oktober 2026 12:01"
    assert news[0].comments == "0"


def test_news_item():
    item = parsers.parse_news_item(load("news_view.html"), "22222222-3333-4444-5555-666666666666")
    assert item.title == "Heating off tomorrow"
    assert item.date_text == "13.10.2026"
    assert item.content_markdown.startswith("Dear all")
    assert "The heating will be *off* from 9 to 12." in item.content_markdown
    for chrome in ("Tekst", "hjemmeskærmen", "Tilbage", "Kommentarer"):
        assert chrome not in item.content_markdown
    assert item.comments_markdown == "* Jane Resident: Thanks for the heads-up!"
    assert [a.name for a in item.attachments] == ["notice.pdf"]


def test_document_folder():
    folder = parsers.parse_document_folder(load("document_archive.html"), None)
    assert folder.path == ["Alle dokumenter", "Current projects"]
    kinds = [(e.kind, e.name, e.date_text, e.added_text) for e in folder.entries]
    assert kinds == [
        ("folder", "Board minutes", "13 Maj 2026", "13 Maj 2026"),
        ("file", "Project proposal.pdf", "15 Okt 2026", "16 Okt 2026"),
    ]


def test_recent_documents():
    recent = parsers.parse_recent_documents(load("document_archive.html"))
    assert len(recent) == 1
    assert recent[0].name == "Project proposal.pdf"
    assert recent[0].date_text == "15 Okt 2026"
    assert recent[0].folder == "Meetings/Extraordinary general meeting"


def test_info_pages():
    html = load("info_page.html")
    assert [p.title for p in parsers.parse_info_page_links(html)] == ["House rules", "Contacts"]
    page = parsers.parse_info_page(html, "77777777-8888-9999-aaaa-bbbbbbbbbbbb")
    assert "No grilling on balconies." in page.content_markdown
    assert page.attachments[0].name == "rules.pdf"
