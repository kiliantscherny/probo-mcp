"""Shared fixtures: a fake ProBo site (respx) serving synthetic HTML fixtures."""

from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
import respx
from mcp.server.mcpserver import MCPServer

from probo_mcp.config import Settings
from probo_mcp.server import create_server

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://example.probo.dk"

MESSAGE_ID = "11111111-2222-3333-4444-555555555555"
NEWS_ID = "22222222-3333-4444-5555-666666666666"
FILE_ID = "44444444-5555-6666-7777-888888888888"
SUBFOLDER_ID = "66666666-7777-8888-9999-000000000000"
SUBFOLDER_FILE_ID = "abababab-cdcd-efef-0101-232323232323"
PAGE_ID = "77777777-8888-9999-aaaa-bbbbbbbbbbbb"
LOGIN_HTML = '<form><input type="hidden" name="csrfmiddlewaretoken" value="tok"></form>'


def load(name: str) -> str:
    return (FIXTURES / name).read_text()


def make_pdf(text: str) -> bytes:
    """A minimal, valid one-page PDF containing ``text``."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


PDF = make_pdf("Hello from the ProBo archive")


def pdf_headers(name: str = "Budget 2026.pdf") -> dict[str, str]:
    return {"content-type": "application/pdf", "content-disposition": f'attachment; filename="{name}"'}


@pytest.fixture
def probo_site() -> Iterator[respx.Router]:
    """Mock every allowlisted ProBo route with fixtures."""
    with respx.mock(base_url=BASE, assert_all_called=False) as site:
        site.get("/member/login/").respond(200, html=LOGIN_HTML, headers={"set-cookie": "csrftoken=tok; Path=/"})
        site.post("/member/login/").respond(302, headers={"location": "/member/"})
        site.get("/member/").respond(200, html=load("home.html"))
        site.get("/member/communication/message/").respond(200, html=load("message_list.html"))
        site.get(f"/member/communication/message/{MESSAGE_ID}/change/").respond(200, html=load("message_thread.html"))
        site.get("/member/communication/news/").respond(200, html=load("news_rows.html"))
        site.get(f"/member/communication/news/{NEWS_ID}/view/").respond(200, html=load("news_view.html"))
        site.get("/member/document_archive/member/").respond(200, html=load("document_archive.html"))
        site.get(f"/member/document_archive/member/{SUBFOLDER_ID}/").respond(200, html=load("subfolder.html"))
        site.get(f"/member/communities/page/{PAGE_ID}/view/").respond(200, html=load("info_page.html"))
        for doc_id in (FILE_ID, SUBFOLDER_FILE_ID):
            path = f"/member/download_file/document_archive/Member/{doc_id}/"
            site.get(path).respond(200, content=PDF, headers=pdf_headers())
            site.head(path).respond(200, headers={**pdf_headers(), "content-length": str(len(PDF))})
        site.route(host="example.probo.dk").respond(404)  # anything else
        yield site


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        base_url=BASE,
        username="resident@example.com",
        password="secret",
        download_dir=tmp_path / "downloads",
        cache_seconds=0,
        confirm_download_mb=10,
    )


@pytest.fixture
def server(settings: Settings, probo_site: respx.Router) -> MCPServer:
    return create_server(lambda: settings)


@pytest.fixture
def server_factory(probo_site: respx.Router) -> Callable[[Callable[[], Settings]], MCPServer]:
    return create_server


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


__all__ = ["BASE", "PDF", "httpx"]
