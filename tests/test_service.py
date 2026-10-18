from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
import respx

from probo_mcp import parsers
from probo_mcp.client import DownloadedFile
from probo_mcp.config import Settings
from probo_mcp.service import ProboService, extract_text, safe_filename

from .conftest import FILE_ID, PDF, SUBFOLDER_FILE_ID


@pytest.fixture
def service(settings: Settings, probo_site: respx.Router) -> ProboService:
    return ProboService.from_settings(settings)


def fake_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the date filter independent of parse_probo_date's implementation."""
    known = {"15 Okt 2026": datetime(2026, 10, 15), "16 Okt 2026": datetime(2026, 10, 16),
             "13 Maj 2026": datetime(2026, 5, 13), "14 Maj 2026": datetime(2026, 5, 14)}  # fmt: skip
    monkeypatch.setattr(parsers, "parse_probo_date", lambda text: known.get(text))


async def test_find_documents_filters_by_added_date(service: ProboService, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_dates(monkeypatch)
    result = await service.find_documents(added_within_days=7, now=datetime(2026, 10, 18))
    assert [d.id for d in result.documents] == [FILE_ID]
    assert result.documents[0].added == datetime(2026, 10, 16)
    assert (result.folders_scanned, result.files_scanned) == (2, 2)
    assert result.note == ""


async def test_find_documents_sorts_newest_first(service: ProboService, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_dates(monkeypatch)
    result = await service.find_documents()
    assert [d.id for d in result.documents] == [FILE_ID, SUBFOLDER_FILE_ID]


async def test_find_documents_reports_unparseable_dates(service: ProboService, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parsers, "parse_probo_date", lambda text: None)
    result = await service.find_documents(added_within_days=7)
    assert result.documents == []
    assert "2 file(s) were skipped" in result.note


async def test_find_documents_respects_folder_limit(service: ProboService) -> None:
    result = await service.find_documents(max_folders=1)
    assert result.folders_scanned == 1
    assert "Stopped after 1 folders" in result.note


async def test_read_document_truncates(settings: Settings, probo_site: respx.Router) -> None:
    service = ProboService.from_settings(replace(settings, max_document_chars=5))
    doc = await service.read_document(FILE_ID)
    assert doc.text == "Hello"
    assert doc.truncated
    assert "Truncated to 5 characters" in doc.note


async def test_save_document_uses_safe_names(service: ProboService, settings: Settings) -> None:
    saved = await service.save_document(FILE_ID, "../../etc/passwd")
    assert Path(saved.path).parent == settings.download_dir
    assert saved.filename == "_.._etc_passwd"


@pytest.mark.parametrize(
    ("file", "expected_text", "note"),
    [
        (DownloadedFile("a.pdf", "application/pdf", PDF), "Hello from the ProBo archive", ""),
        (DownloadedFile("a.txt", "text/plain", "æøå".encode()), "æøå", ""),
        (DownloadedFile("a.docx", "application/msword", b"x"), None, "not supported"),
        (DownloadedFile("broken.pdf", "application/pdf", b"%PDF-garbage"), None, "Could not read"),
    ],
)
def test_extract_text(file: DownloadedFile, expected_text: str | None, note: str) -> None:
    text, got_note = extract_text(file)
    assert text == expected_text
    assert note in got_note


def test_extract_text_scanned_pdf() -> None:
    from .conftest import make_pdf

    text, note = extract_text(DownloadedFile("scan.pdf", "application/pdf", make_pdf("")))
    assert text is None
    assert "no extractable text" in note


@pytest.mark.parametrize(("name", "safe"), [("a/b\\c.pdf", "a_b_c.pdf"), ("...", "document"), (".env", "env")])
def test_safe_filename(name: str, safe: str) -> None:
    assert safe_filename(name) == safe
