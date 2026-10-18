"""HTTP client for a ProBo association site.

ProBo has no public JSON API: it is a server-rendered Django + HTMX app. This
client fetches HTML pages (and HTMX partials) with a logged-in session.

Read-only by construction: the public fetch methods are GET/HEAD-based and
refuse any path that is not on an explicit allowlist. Several plain links in
ProBo change state (e.g. ``toggle_subscription/``), so never follow arbitrary
URLs found in page content. The single POST is the login form.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import unquote

import httpx

logger = logging.getLogger(__name__)

UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
UUID_RE = re.compile(rf"^{UUID}$")

LOGIN_PATH = "/member/login/"

ALLOWED_PAGES = [
    re.compile(p)
    for p in (
        r"^/member/$",
        r"^/member/communication/message/$",
        rf"^/member/communication/message/{UUID}/change/$",
        r"^/member/communication/news/$",
        rf"^/member/communication/news/{UUID}/view/$",
        r"^/member/document_archive/member/$",
        rf"^/member/document_archive/member/{UUID}/$",
        rf"^/member/communities/page/{UUID}/view/$",
    )
]
ALLOWED_DOWNLOADS = [re.compile(rf"^/member/download_file/\w+/\w+/{UUID}/$")]


class ProboError(RuntimeError):
    """Base error for ProBo access problems."""


class NotAllowedError(ProboError):
    """Raised when a path is outside the read-only allowlist."""


class LoginError(ProboError):
    """Raised when logging in to ProBo fails."""


@dataclass(frozen=True)
class DownloadedFile:
    """A file fetched from ProBo."""

    filename: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class FileInfo:
    """Metadata about a downloadable file, from a HEAD request."""

    filename: str
    content_type: str
    size_bytes: int | None


def check_allowed(path: str, allowlist: list[re.Pattern[str]]) -> None:
    """Raise `NotAllowedError` unless ``path`` matches the allowlist."""
    if not any(p.match(path) for p in allowlist):
        raise NotAllowedError(f"Refusing to fetch {path!r}: not an allowlisted read-only ProBo route")


def filename_from_disposition(header: str, fallback: str) -> str:
    """Extract a filename from a ``Content-Disposition`` header (RFC 6266 / 5987)."""
    m = re.search(r"filename\*\s*=\s*[^']*''([^;]+)", header)
    if m:
        return unquote(m.group(1).strip().strip('"'))
    m = re.search(r'filename\s*=\s*"?([^";]+)"?', header)
    return m.group(1).strip() if m else fallback


def require_uuid(value: str, what: str = "id") -> str:
    """Validate and normalise a ProBo object id."""
    value = value.strip()
    if not UUID_RE.match(value):
        raise ValueError(f"Invalid {what}: expected a UUID, got {value!r}")
    return value.lower()


def download_path(document: str) -> str:
    """Accept a document UUID or an attachment ``path`` and return the allowlisted download path."""
    document = document.strip()
    if document.startswith("/"):
        check_allowed(document, ALLOWED_DOWNLOADS)
        return document
    return f"/member/download_file/document_archive/Member/{require_uuid(document, 'document id')}/"


class ProboClient:
    """Read-only, logged-in access to one ProBo association site."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        cache_seconds: float = 60,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        """Create a client; nothing is fetched until the first request."""
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            follow_redirects=True,
            timeout=30,
            headers={"User-Agent": "probo-mcp (read-only; +https://github.com/kiliantscherny/probo-mcp)"},
            transport=transport,
        )
        self._logged_in = False
        self._login_lock = asyncio.Lock()
        self._cache_seconds = cache_seconds
        self._cache: dict[tuple[str, tuple[tuple[str, str], ...], bool], tuple[float, str]] = {}

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._http.aclose()

    def web_url(self, path: str) -> str:
        """Absolute browser URL for a ProBo path (for "open in ProBo" links)."""
        return f"{self.base_url}{path}"

    # -- auth -------------------------------------------------------------

    @staticmethod
    def _is_login_page(resp: httpx.Response) -> bool:
        return resp.url.path.startswith(LOGIN_PATH)

    async def _login(self, *, force: bool = False) -> None:
        async with self._login_lock:
            if self._logged_in and not force:
                return  # another task logged in while we waited
            logger.info("Logging in to %s", self.base_url)
            page = await self._http.get(LOGIN_PATH)
            page.raise_for_status()
            token = self._http.cookies.get("csrftoken")
            if not token:
                m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text)
                token = m.group(1) if m else None
            if not token:
                raise LoginError("Could not find a CSRF token on the ProBo login page")

            resp = await self._http.post(
                LOGIN_PATH,
                data={
                    "csrfmiddlewaretoken": token,
                    "username": self._username,
                    "password": self._password,
                    "next": "/member/",
                },
                headers={"Referer": self.web_url(LOGIN_PATH), "Origin": self.base_url},
            )
            if resp.status_code >= 400 or self._is_login_page(resp):
                raise LoginError(
                    "ProBo login failed. Check PROBO_USERNAME / PROBO_PASSWORD "
                    "(accounts requiring MitID or 2FA are not supported)."
                )
            self._logged_in = True

    async def _request(
        self, method: str, path: str, params: dict[str, str] | None, headers: dict[str, str] | None
    ) -> httpx.Response:
        if not self._logged_in:
            await self._login()
        resp = await self._http.request(method, path, params=params, headers=headers)
        if self._is_login_page(resp):  # session expired
            logger.info("Session expired; logging in again")
            self._logged_in = False
            await self._login(force=True)
            resp = await self._http.request(method, path, params=params, headers=headers)
            if self._is_login_page(resp):
                raise LoginError("Still redirected to login after re-authenticating")
        if resp.status_code == 404:
            raise ProboError(f"Not found: {path}")
        resp.raise_for_status()
        return resp

    # -- public, read-only API -------------------------------------------

    async def get_html(self, path: str, params: dict[str, str] | None = None, *, htmx: bool = False) -> str:
        """GET an allowlisted page. With ``htmx=True`` the server returns only the partial (e.g. list rows)."""
        check_allowed(path, ALLOWED_PAGES)
        clean = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        key = (path, tuple(sorted(clean.items())), htmx)
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < self._cache_seconds:
            return cached[1]
        resp = await self._request("GET", path, clean, {"HX-Request": "true"} if htmx else None)
        if self._cache_seconds > 0:
            self._cache[key] = (time.monotonic(), resp.text)
        return resp.text

    async def file_info(self, path: str) -> FileInfo:
        """HEAD an allowlisted download to learn its name, type and size without fetching it."""
        check_allowed(path, ALLOWED_DOWNLOADS)
        resp = await self._request("HEAD", path, None, None)
        length = resp.headers.get("content-length")
        return FileInfo(
            filename=filename_from_disposition(resp.headers.get("content-disposition", ""), _last_segment(path)),
            content_type=_content_type(resp),
            size_bytes=int(length) if length and length.isdigit() else None,
        )

    async def download(self, path: str) -> DownloadedFile:
        """GET an allowlisted download and return its bytes."""
        check_allowed(path, ALLOWED_DOWNLOADS)
        resp = await self._request("GET", path, None, None)
        content_type = _content_type(resp)
        if content_type == "text/html":
            raise ProboError(f"Expected a file at {path} but got an HTML page")
        filename = filename_from_disposition(resp.headers.get("content-disposition", ""), _last_segment(path))
        return DownloadedFile(filename=filename, content_type=content_type, content=resp.content)


def _content_type(resp: httpx.Response) -> str:
    return resp.headers.get("content-type", "application/octet-stream").split(";")[0].strip()


def _last_segment(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1]
