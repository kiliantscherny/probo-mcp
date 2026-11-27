import httpx
import pytest
from starlette.types import Message, Receive, Scope, Send

from probo_mcp.http_auth import RequireToken, new_token

TOKEN = new_token()


async def ok_app(scope: Scope, receive: Receive, send: Send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(RequireToken(ok_app, TOKEN)), base_url="http://test")


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": f"Bearer {TOKEN[:-1]}"}, {"Authorization": f"Basic {TOKEN}"}, {"Authorization": TOKEN}],
)
async def test_refuses_requests_without_the_token(headers: dict[str, str]) -> None:
    async with client() as c:
        resp = await c.post("/mcp", headers=headers)
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("scheme", ["Bearer", "bearer"])
async def test_passes_requests_with_the_token(scheme: str) -> None:
    async with client() as c:
        resp = await c.post("/mcp", headers={"Authorization": f"{scheme} {TOKEN}"})
    assert resp.status_code == 200
    assert resp.text == "ok"


async def test_lifespan_events_pass_through() -> None:
    seen = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    async def receive() -> Message:
        return {}

    async def send(message: Message) -> None:
        pass

    await RequireToken(app, TOKEN)({"type": "lifespan"}, receive, send)
    assert seen == ["lifespan"]
