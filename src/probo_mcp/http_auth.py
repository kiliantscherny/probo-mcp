"""A bearer-token check in front of the streamable HTTP transport.

Without it, anyone who can reach the port can read the association's ProBo with the configured login.
Over stdio (what Claude Desktop and Claude Code use) there is no port, so none of this applies.
"""

from __future__ import annotations

import hmac
import secrets

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

#: Shortest PROBO_HTTP_TOKEN accepted; `new_token` makes 43 characters.
MIN_TOKEN_LENGTH = 32


def new_token() -> str:
    """A random token for this run (256 bits)."""
    return secrets.token_urlsafe(32)


class RequireToken:
    """ASGI middleware that refuses HTTP requests without ``Authorization: Bearer <token>``."""

    def __init__(self, app: ASGIApp, token: str):
        """Wrap ``app``; ``token`` is the only credential accepted."""
        self.app = app
        self._token = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Check the header on HTTP requests; lifespan events pass straight through."""
        if scope["type"] == "http" and not self._authorised(scope):
            response = PlainTextResponse("Missing or wrong bearer token.", 401, headers={"WWW-Authenticate": "Bearer"})
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _authorised(self, scope: Scope) -> bool:
        header = next((v for k, v in scope["headers"] if k == b"authorization"), b"")
        scheme, _, value = header.partition(b" ")
        # compare_digest takes as long for a near miss as for a wild guess, so timing gives nothing away.
        return scheme.lower() == b"bearer" and hmac.compare_digest(value.strip(), self._token)
