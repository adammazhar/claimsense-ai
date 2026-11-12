"""The co-pilot's side of the MCP door: one connection per request, under the adjuster's own token.

The connection is the Agents SDK's `MCPServerStreamableHttp`. Pipeline code calls tools on it directly,
and the searching agents' one tool, `search_clauses`, calls the door over the same connection
(agent_defs.door_search_tool, D-031, D-032). Identity travels as the bearer token on the transport; the
correlation ID travels as a header. Neither is a tool argument.

Two connectors, one protocol:
- HttpDoorConnector: the door as a service (compose), at DOOR_URL.
- InProcessDoorConnector: the same door, served in process over an ASGI transport (tests and evals),
  so CI exercises the real MCP protocol, auth and gate with no ports.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx2
from agents.mcp import MCPServerStreamableHttp

from .contracts import RETRYABLE, DoorError, DoorErrorCode

DEFAULT_DOOR_URL = "http://localhost:8010/mcp"
CORRELATION_HEADER = "X-Correlation-Id"


class DoorCallError(Exception):
    """A tool call the door refused or couldn't serve, carrying its structured error."""

    def __init__(self, error: DoorError) -> None:
        super().__init__(f"{error.code.value}: {error.message}")
        self.error = error


def _status_in_chain(exc: BaseException) -> int | None:
    """The HTTP status behind a transport failure, if any (the SDK wraps it in groups and UserErrors)."""
    seen, stack = set(), [exc]
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        response = getattr(current, "response", None)
        if response is not None and getattr(response, "status_code", None):
            return response.status_code
        text = str(current)
        for code in (401, 403):
            if f"HTTP error {code}" in text or f"'{code} " in text or f" {code} Unauthorized" in text:
                return code
        stack += list(getattr(current, "exceptions", ()) or ())
        stack += [e for e in (current.__cause__, current.__context__) if e is not None]
    return None


def _local_error(code: DoorErrorCode, correlation_id: str | None, message: str) -> DoorError:
    return DoorError(code=code, message=message, retryable=code in RETRYABLE, correlation_id=correlation_id,
                     request_id=f"local-{random.randrange(16**8):08x}")


@dataclass
class DoorConnection:
    server: MCPServerStreamableHttp
    correlation_id: str
    attempts: int = 3
    backoff_seconds: float = 0.1
    max_wait_seconds: float = 5.0  # a longer retry_after goes back to the caller rather than stalling the request

    async def call(self, tool: str, **arguments) -> Any:
        """Call a door tool from code. Retryable errors back off and retry; every attempt is audited by
        the door. A write is safe to retry because it carries its idempotency key (D-037)."""
        return json.loads(await self.call_text(tool, **arguments))

    async def call_text(self, tool: str, **arguments) -> str:
        """The same retrying call, returning the door's text as it came. Raises DoorCallError."""
        for attempt in range(self.attempts):
            try:
                result = await self.server.call_tool(tool, arguments)
            except Exception as exc:  # transport failure: the door is unreachable
                if _status_in_chain(exc) == 401:
                    raise DoorCallError(_local_error(DoorErrorCode.UNAUTHENTICATED, self.correlation_id,
                                                     "A valid seat token is required.")) from exc
                error = _local_error(DoorErrorCode.UPSTREAM_UNAVAILABLE, self.correlation_id,
                                     "The MCP door is unavailable. Nothing was changed.")
            else:
                text = result.content[0].text if result.content else ""
                if not result.is_error:
                    return text
                try:
                    error = DoorError.model_validate_json(text)
                except ValueError:
                    error = _local_error(DoorErrorCode.UPSTREAM_UNAVAILABLE, self.correlation_id,
                                         "The door returned an unstructured error.")
            wait = (error.retry_after if error.retry_after is not None
                    else self.backoff_seconds * 2 ** attempt * (1 + random.random()))
            if not error.retryable or attempt == self.attempts - 1 or wait > self.max_wait_seconds:
                raise DoorCallError(error)
            await asyncio.sleep(wait)
        raise AssertionError("unreachable")


class _Statuses:
    """Watches the transport's responses: the SDK client reports a 401 only as a generic MCPError."""

    def __init__(self, transport=None) -> None:
        self.transport, self.unauthorized = transport, False

    def factory(self, headers=None, timeout=None, auth=None):
        async def on_response(response: httpx2.Response) -> None:
            if response.status_code == 401:
                self.unauthorized = True

        kwargs = {"transport": self.transport, "base_url": "http://door"} if self.transport else {}
        return httpx2.AsyncClient(headers=headers, timeout=timeout, auth=auth, follow_redirects=False,
                                  event_hooks={"response": [on_response]}, **kwargs)


def _server(url: str, token: str, correlation_id: str, tool_filter, statuses: _Statuses) -> MCPServerStreamableHttp:
    headers = {"Authorization": f"Bearer {token}", CORRELATION_HEADER: correlation_id}
    return MCPServerStreamableHttp(
        params={"url": url, "headers": headers, "timeout": 30, "sse_read_timeout": 300,
                "httpx_client_factory": statuses.factory},
        name="claimsense-door", cache_tools_list=True, tool_filter=tool_filter,
        client_session_timeout_seconds=60, max_retry_attempts=2, retry_backoff_seconds_base=0.2)


async def _open(stack: AsyncExitStack, server: MCPServerStreamableHttp, correlation_id: str,
                statuses: _Statuses) -> DoorConnection:
    try:
        await stack.enter_async_context(server)
    except Exception as exc:
        if statuses.unauthorized or _status_in_chain(exc) == 401:
            raise DoorCallError(_local_error(DoorErrorCode.UNAUTHENTICATED, correlation_id,
                                             "A valid seat token is required.")) from None
        raise DoorCallError(_local_error(DoorErrorCode.UPSTREAM_UNAVAILABLE, correlation_id,
                                         "The MCP door is unavailable. Nothing was changed.")) from None
    return DoorConnection(server, correlation_id)


def _single_leaf(group: BaseExceptionGroup) -> BaseException | None:
    leaves, stack = [], [group]
    while stack:
        current = stack.pop()
        if isinstance(current, BaseExceptionGroup):
            stack += list(current.exceptions)
        else:
            leaves.append(current)
    return leaves[0] if len(leaves) == 1 else None


@asynccontextmanager
async def _unwrapped() -> AsyncIterator[None]:
    """anyio task groups wrap whatever the caller raised; hand the caller back its own exception."""
    try:
        yield
    except BaseExceptionGroup as group:
        leaf = _single_leaf(group)
        if leaf is None:
            raise
        raise leaf from None


@dataclass
class HttpDoorConnector:
    url: str = DEFAULT_DOOR_URL

    @classmethod
    def from_env(cls) -> HttpDoorConnector:
        return cls(os.environ.get("DOOR_URL", DEFAULT_DOOR_URL))

    @asynccontextmanager
    async def connect(self, token: str, correlation_id: str, tool_filter=None) -> AsyncIterator[DoorConnection]:
        statuses = _Statuses()
        async with _unwrapped(), AsyncExitStack() as stack:
            server = _server(self.url, token, correlation_id, tool_filter, statuses)
            yield await _open(stack, server, correlation_id, statuses)


@dataclass
class InProcessDoorConnector:
    """The real door app, built fresh per connection over the door's shared state."""

    door: Any  # claimsense.door.Door; typed loosely so the co-pilot doesn't import the door's backends

    @asynccontextmanager
    async def connect(self, token: str, correlation_id: str, tool_filter=None) -> AsyncIterator[DoorConnection]:
        mcp, app = self.door.build()
        statuses = _Statuses(transport=httpx2.ASGITransport(app=app))
        async with _unwrapped(), AsyncExitStack() as stack:
            await stack.enter_async_context(mcp.session_manager.run())
            server = _server("http://door/mcp", token, correlation_id, tool_filter, statuses)
            yield await _open(stack, server, correlation_id, statuses)
