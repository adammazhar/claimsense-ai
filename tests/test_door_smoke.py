"""Smoke test (M4, decision 1): the openai-agents MCP client reaches a v2 MCPServer over
streamable HTTP with a bearer token, and the tool sees the identity the token resolves to.

This runs before anything else is built on the SDK pair. It uses a real socket (uvicorn on an
ephemeral localhost port), not an in-memory transport, because get_access_token() is only
populated by the HTTP auth middleware.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import socket
import threading
import time

import pytest
import uvicorn
from agents.mcp import MCPServerStreamableHttp
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer

GOOD_TOKEN = "smoke-" + "a" * 40
SEATS = {hashlib.sha256(GOOD_TOKEN.encode()).hexdigest(): ("adj-004", "adjuster_bi")}


class _Verifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        seat = SEATS.get(hashlib.sha256(token.encode()).hexdigest())
        if seat is None:
            return None
        user, role = seat
        return AccessToken(token=token, client_id=user, scopes=[role], subject=user)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def door_url():
    port = _free_port()
    server = MCPServer(
        "smoke-door",
        token_verifier=_Verifier(),
        auth=AuthSettings(
            issuer_url="http://127.0.0.1",
            resource_server_url=f"http://127.0.0.1:{port}/mcp",
            required_scopes=[],
            # Seat tokens are opaque and not audience-bound; the verifier checks the seat itself.
            validate_token_resource=False,
        ),
    )

    @server.tool()
    def whoami() -> dict:
        tok = get_access_token()
        return {"user": tok.subject if tok else None, "scopes": tok.scopes if tok else None}

    app = server.streamable_http_app(host="127.0.0.1")
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    uv = uvicorn.Server(config)
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not uv.started:
        if time.time() > deadline:
            raise RuntimeError("smoke door did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp"
    uv.should_exit = True
    thread.join(timeout=5)


async def _call(url: str, token: str | None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with MCPServerStreamableHttp(
        params={"url": url, "headers": headers, "timeout": 10}, cache_tools_list=True
    ) as srv:
        tools = await srv.list_tools()
        result = await srv.call_tool("whoami", {})
        return [t.name for t in tools], result


def test_agents_client_reaches_v2_server_with_bearer_identity(door_url):
    names, result = asyncio.run(_call(door_url, GOOD_TOKEN))
    assert names == ["whoami"]
    assert not result.is_error
    payload = result.structured_content or json.loads(result.content[0].text)
    assert payload == {"user": "adj-004", "scopes": ["adjuster_bi"]}


@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_missing_or_bad_token_is_refused(door_url, token):
    with pytest.raises(BaseException):
        asyncio.run(_call(door_url, token))


@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_missing_or_bad_token_gets_401_at_the_transport(door_url, token):
    import httpx2

    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    resp = httpx2.post(door_url, headers=headers, json=body, timeout=10)
    assert resp.status_code == 401
