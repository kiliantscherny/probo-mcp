import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
import respx

from probo_mcp import parsers
from probo_mcp.client import DownloadedFile
from probo_mcp.config import Settings
from probo_mcp.parsers import PROBO_TZ
from probo_mcp.service import ProboService, extract_text, safe_filename

from .conftest import FILE_ID, PDF, SUBFOLDER_FILE_ID


@pytest.fixture
def service(settings: Settings, probo_site: respx.Router) -> ProboService:
    return ProboService.from_settings(settings)


def fake_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the date filter independent of parse_probo_date's implementation."""
    known = {
        "15 Okt 2026": datetime(2026, 10, 15, tzinfo=PROBO_TZ),
        "16 Okt 2026": datetime(2026, 10, 16, tzinfo=PROBO_TZ),
        "13 Maj 2026": datetime(2026, 5, 13, tzinfo=PROBO_TZ),
        "14 Maj 2026": datetime(2026, 5, 14, tzinfo=PROBO_TZ),
    }
    monkeypatch.setattr(parsers, "parse_probo_date", lambda text: known.get(text))


async def test_find_documents_filters_by_added_date(service: ProboService, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_dates(monkeypatch)
    result = await service.find_documents(added_within_days=7, now=datetime(2026, 10, 18, tzinfo=PROBO_TZ))
    assert [d.id for d in result.documents] == [FILE_ID]
    assert result.documents[0].added == datetime(2026, 10, 16, tzinfo=PROBO_TZ)
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
    assert Path(saved.path).parent == settings.download_dir.resolve()
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


@pytest.mark.parametrize(
    ("name", "safe"),
    [
        ("a/b\\c.pdf", "a_b_c.pdf"),
        ("...", "document"),
        (".env", "env"),
        ('C:report<1>|"2"?*.pdf', "C_report_1___2___.pdf"),
        ("Referat æøå (endelig).pdf", "Referat æøå (endelig).pdf"),
        ("CON.pdf", "_CON.pdf"),
        ("lpt1", "_lpt1"),
        ("trailing. ", "trailing"),
        ("x" * 300, "x" * 200),
    ],
)
def test_safe_filename(name: str, safe: str) -> None:
    assert safe_filename(name) == safe


def test_pdf_text_keeps_table_rows_and_falls_back_to_plain() -> None:
    from probo_mcp.service import _page_text

    class Page:
        def __init__(self, layout: str | Exception, plain: str = "plain text"):
            self.layout, self.plain = layout, plain

        def extract_text(self, extraction_mode: str = "plain") -> str:
            if extraction_mode == "layout":
                if isinstance(self.layout, Exception):
                    raise self.layout
                return self.layout
            return self.plain

    table = "  Fællesbidrag          kr.        5.340.000     5.193.000  \n\n\n\nNext"
    assert _page_text(Page(table)) == "Fællesbidrag   kr.   5.340.000   5.193.000\n\nNext"  # ty: ignore[invalid-argument-type]
    assert _page_text(Page(ZeroDivisionError())) == "plain text"  # ty: ignore[invalid-argument-type]


@pytest.mark.skipif(sys.platform == "win32", reason="creating symlinks needs extra rights on Windows")
def test_writes_replace_a_planted_symlink_instead_of_following_it(tmp_path: Path) -> None:
    from probo_mcp.service import _write_file

    outside = tmp_path / "outside.txt"
    outside.write_text("keep me", encoding="utf-8")
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "thread.md").symlink_to(outside)
    _write_file(archive / "thread.md", b"new")
    assert outside.read_text(encoding="utf-8") == "keep me"
    assert not (archive / "thread.md").is_symlink()
    assert (archive / "thread.md").read_bytes() == b"new"
    assert [p.name for p in archive.iterdir()] == ["thread.md"]  # no temporary files left


def test_downloaded_files_are_marked_as_from_the_internet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from probo_mcp import service as service_module

    calls = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: calls.append(argv))
    service_module._write_file(tmp_path / "a.pdf", b"%PDF", True)
    service_module._write_file(tmp_path / "thread.md", b"# notes")
    assert len(calls) == 1
    assert calls[0][:3] == ["/usr/bin/xattr", "-w", "com.apple.quarantine"]


def test_pdf_text_falls_back_to_plain_when_layout_loses_text() -> None:
    from probo_mcp.service import _page_text

    class Rotated:
        def extract_text(self, extraction_mode: str = "plain") -> str:
            return "Header" if extraction_mode == "layout" else "Header Sideways column titles"

    assert _page_text(Rotated()) == "Header Sideways column titles"  # ty: ignore[invalid-argument-type]
