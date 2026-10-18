"""Per-server state shared through the MCP lifespan, and error translation for handlers."""

import functools
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .client import LoginError, NotAllowedError, ProboError
from .config import ConfigError, Settings
from .service import ProboService

logger = logging.getLogger(__name__)


class AppState:
    """Holds the lazily created `ProboService`.

    The service is created on first use rather than at startup, so a server with
    missing settings still starts and every tool explains what to configure
    instead of the client showing an opaque "server failed to start".
    """

    def __init__(self, settings_factory: Callable[[], Settings] = Settings.from_env):
        """Create state that builds settings with ``settings_factory`` on first use."""
        self._settings_factory = settings_factory
        self._service: ProboService | None = None

    def service(self) -> ProboService:
        """Return the shared service, creating it on first use."""
        if self._service is None:
            self._service = ProboService.from_settings(self._settings_factory())
        return self._service

    async def aclose(self) -> None:
        """Close the service if it was created (it is recreated on next use)."""
        service, self._service = self._service, None
        if service is not None:
            await service.aclose()


def lifespan_for(state: AppState) -> Callable[[MCPServer], Any]:
    """Build an MCP lifespan that exposes ``state`` to handlers and closes it on shutdown.

    The state is created by the caller (not inside the lifespan) so handlers that
    receive no request context, such as completion handlers, can share it too.
    """

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncGenerator[AppState]:
        try:
            yield state
        finally:
            await state.aclose()

    return lifespan


def service_from(ctx: Context) -> ProboService:
    """Get the `ProboService` for the current request."""
    state = ctx.request_context.lifespan_context
    if not isinstance(state, AppState):  # pragma: no cover - wiring error
        raise TypeError("probo-mcp lifespan state is missing")
    return state.service()


def user_errors[**P, R](fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Turn expected failures into `ToolError`s, which the client shows the model as a tool error.

    Anything else is a bug and propagates (the SDK logs the traceback).
    """

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await fn(*args, **kwargs)
        except ConfigError as e:
            raise ToolError(f"probo-mcp is not configured: {e}") from e
        except LoginError as e:
            raise ToolError(str(e)) from e
        except NotAllowedError as e:
            raise ToolError(str(e)) from e
        except ProboError as e:
            raise ToolError(f"ProBo request failed: {e}") from e
        except ValueError as e:  # invalid ids and similar argument problems
            raise ToolError(str(e)) from e
        except httpx.HTTPError as e:
            logger.warning("HTTP error talking to ProBo: %s", e)
            raise ToolError(f"Could not reach ProBo: {e}") from e

    return wrapper
