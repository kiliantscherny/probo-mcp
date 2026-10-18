import httpx
import pytest
import respx

from probo_mcp.client import LoginError, NotAllowedError, ProboClient

BASE = "https://example.probo.dk"
LOGIN_HTML = '<form><input type="hidden" name="csrfmiddlewaretoken" value="tok"></form>'


def mock_login(router: respx.Router, ok: bool = True) -> respx.Route:
    router.get(f"{BASE}/member/login/").respond(200, html=LOGIN_HTML, headers={"set-cookie": "csrftoken=tok; Path=/"})
    if ok:
        router.post(f"{BASE}/member/login/").respond(
            302, headers={"location": "/member/", "set-cookie": "sessionid=s; Path=/"}
        )
    else:
        router.post(f"{BASE}/member/login/").respond(200, html=LOGIN_HTML)
    return router.routes[-1]


@pytest.fixture
def router():
    with respx.mock(assert_all_called=False) as r:
        yield r


async def test_logs_in_then_fetches_htmx_partial(router):
    login = mock_login(router)
    router.get(f"{BASE}/member/").respond(200, html="<p>home</p>")
    page = router.get(f"{BASE}/member/communication/message/").respond(200, html="<div>rows</div>")

    client = ProboClient(BASE, "u", "p")
    html = await client.get_html("/member/communication/message/", {"p": "2", "q": ""}, htmx=True)

    assert html == "<div>rows</div>"
    assert login.call_count == 1
    sent = login.calls[0].request
    assert b"username=u" in sent.content
    assert b"csrfmiddlewaretoken=tok" in sent.content
    assert sent.headers["referer"] == f"{BASE}/member/login/"
    req = page.calls[0].request
    assert req.headers["hx-request"] == "true"
    assert req.url.params == httpx.QueryParams({"p": "2"})  # empty params dropped


async def test_relogs_in_when_session_expires(router):
    login = mock_login(router)
    router.get(f"{BASE}/member/").respond(200, html="home")
    router.get(f"{BASE}/member/communication/news/").mock(
        side_effect=[
            httpx.Response(302, headers={"location": "/member/login/?next=/x"}),
            httpx.Response(200, html="news"),
        ]
    )
    client = ProboClient(BASE, "u", "p")
    client._logged_in = True  # pretend we had a session that has now expired

    assert await client.get_html("/member/communication/news/") == "news"
    assert login.call_count == 1


async def test_bad_credentials(router):
    mock_login(router, ok=False)
    with pytest.raises(LoginError):
        await ProboClient(BASE, "u", "wrong").get_html("/member/")


@pytest.mark.parametrize(
    "path",
    [
        "/member/communication/message/toggle_subscription/11111111-2222-3333-4444-555555555555/",
        "/member/communication/message/actions_view_post/",
        "/member/properties/residentcommunitymember/",
        "/member/password_change/",
        "/member/communication/message/../password_change/",
    ],
)
async def test_allowlist_blocks_non_read_routes(router, path):
    client = ProboClient(BASE, "u", "p")
    with pytest.raises(NotAllowedError):
        await client.get_html(path)
    assert not router.calls  # refused before any network request


async def test_download_filename_from_content_disposition(router):
    mock_login(router)
    router.get(f"{BASE}/member/").respond(200, html="home")
    path = "/member/download_file/document_archive/Member/44444444-5555-6666-7777-888888888888/"
    router.get(f"{BASE}{path}").respond(
        200,
        content=b"%PDF-1.4",
        headers={
            "content-type": "application/pdf",
            "content-disposition": "attachment; filename*=UTF-8''Referat%20%C3%A6%C3%B8.pdf",
        },
    )
    f = await ProboClient(BASE, "u", "p").download(path)
    assert f.filename == "Referat æø.pdf"
    assert f.content_type == "application/pdf"


async def test_concurrent_requests_log_in_once(router):
    import asyncio

    login = mock_login(router)
    router.get(f"{BASE}/member/").respond(200, html="home")
    client = ProboClient(BASE, "u", "p")
    await asyncio.gather(*(client.get_html("/member/") for _ in range(5)))
    assert login.call_count == 1


async def test_cache_serves_repeat_requests(router):
    mock_login(router)
    router.get(f"{BASE}/member/").respond(200, html="home")  # where login redirects
    news = router.get(f"{BASE}/member/communication/news/").respond(200, html="rows")
    client = ProboClient(BASE, "u", "p", cache_seconds=60)
    first = await client.get_html("/member/communication/news/", {"p": "1"}, htmx=True)
    again = await client.get_html("/member/communication/news/", {"p": "1"}, htmx=True)
    assert first == again == "rows"
    assert news.call_count == 1
    await client.get_html("/member/communication/news/", {"p": "2"}, htmx=True)  # different key
    assert news.call_count == 2

    uncached = ProboClient(BASE, "u", "p", cache_seconds=0)
    await uncached.get_html("/member/communication/news/")
    await uncached.get_html("/member/communication/news/")
    assert news.call_count == 4


async def test_file_info_uses_head(router):
    mock_login(router)
    router.get(f"{BASE}/member/").respond(200, html="home")
    path = "/member/download_file/document_archive/Member/44444444-5555-6666-7777-888888888888/"
    head = router.head(f"{BASE}{path}").respond(
        200,
        headers={
            "content-type": "application/pdf",
            "content-length": "1234",
            "content-disposition": 'attachment; filename="a.pdf"',
        },
    )
    info = await ProboClient(BASE, "u", "p").file_info(path)
    assert (info.filename, info.content_type, info.size_bytes) == ("a.pdf", "application/pdf", 1234)
    assert head.call_count == 1


async def test_download_rejects_html(router):
    from probo_mcp.client import ProboError

    mock_login(router)
    router.get(f"{BASE}/member/").respond(200, html="home")
    path = "/member/download_file/document_archive/Member/44444444-5555-6666-7777-888888888888/"
    router.get(f"{BASE}{path}").respond(200, html="<html>oops</html>")
    with pytest.raises(ProboError, match="got an HTML page"):
        await ProboClient(BASE, "u", "p").download(path)


async def test_missing_csrf_token(router):
    router.get(f"{BASE}/member/login/").respond(200, html="<p>maintenance</p>")
    with pytest.raises(LoginError, match="CSRF"):
        await ProboClient(BASE, "u", "p").get_html("/member/")


async def test_csrf_token_from_form_when_no_cookie(router):
    router.get(f"{BASE}/member/login/").respond(200, html=LOGIN_HTML)
    login = router.post(f"{BASE}/member/login/").respond(302, headers={"location": "/member/"})
    router.get(f"{BASE}/member/").respond(200, html="home")
    await ProboClient(BASE, "u", "p").get_html("/member/")
    assert b"csrfmiddlewaretoken=tok" in login.calls[0].request.content


async def test_still_on_login_after_relogin(router):
    router.get(f"{BASE}/member/login/").respond(200, html=LOGIN_HTML, headers={"set-cookie": "csrftoken=tok; Path=/"})
    router.post(f"{BASE}/member/login/").respond(302, headers={"location": "/member/communication/news/"})
    router.get(f"{BASE}/member/communication/news/").respond(200, html="news")
    router.get(f"{BASE}/member/").respond(302, headers={"location": "/member/login/"})
    client = ProboClient(BASE, "u", "p")
    client._logged_in = True
    with pytest.raises(LoginError, match="Still redirected"):
        await client.get_html("/member/")


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ('attachment; filename="plain.pdf"', "plain.pdf"),
        ("attachment; filename=bare.pdf", "bare.pdf"),
        ("attachment; filename*=UTF-8''%C3%86bler.pdf", "Æbler.pdf"),
        ("", "fallback"),
    ],
)
def test_filename_from_disposition(header, expected):
    from probo_mcp.client import filename_from_disposition

    assert filename_from_disposition(header, "fallback") == expected


def test_download_path_accepts_ids_and_allowlisted_paths():
    from probo_mcp.client import download_path

    doc = "44444444-5555-6666-7777-888888888888"
    assert download_path(doc.upper()) == f"/member/download_file/document_archive/Member/{doc}/"
    attachment = f"/member/download_file/message/Attachment/{doc}/"
    assert download_path(attachment) == attachment
    with pytest.raises(NotAllowedError):
        download_path("/member/password_change/")
    with pytest.raises(ValueError, match="expected a UUID"):
        download_path("nope")
