"""Structured errors an agent or the API can reason about, with retry and backoff on reads (D-037)."""

from __future__ import annotations

import httpx
import pytest

from claimsense.contracts import DoorErrorCode
from claimsense.door import RateLimiter
from claimsense.door_client import DoorCallError
from claimsense.mock_services import create_documents_app
from conftest import ADJ1, APPROVE_CLAIM, SUPERVISOR, Stack


async def _call(stack: Stack, seat: str, tool: str, **arguments):
    async with stack.connector.connect(stack.tokens[seat], f"err-{tool}") as door:
        try:
            return await door.call(tool, **arguments), None
        except DoorCallError as refused:
            return None, refused.error


def test_not_found_only_for_a_supervisor(run) -> None:
    stack = Stack()
    _, supervisor = run(_call(stack, SUPERVISOR, "get_claim", claim_id="CLM-2026-9999"))
    _, adjuster = run(_call(stack, ADJ1, "get_claim", claim_id="CLM-2026-9999"))
    assert supervisor.code is DoorErrorCode.NOT_FOUND and not supervisor.retryable
    assert adjuster.code is DoorErrorCode.FORBIDDEN_SCOPE


def test_forbidden_scope_carries_a_hint_and_the_ids_to_find_its_audit_row(run) -> None:
    stack = Stack()
    _, error = run(_call(stack, ADJ1, "get_claim", claim_id="CLM-2026-0011"))
    assert error.code is DoorErrorCode.FORBIDDEN_SCOPE
    assert error.hint and "audit" in error.hint
    row = stack.audit_rows[-1]
    assert (row["request_id"], row["correlation_id"], row["decision"]) == (error.request_id, error.correlation_id, "deny")


def test_rate_limited_says_when_to_retry(run) -> None:
    stack = Stack(limiter=RateLimiter(capacity=1, refill_per_second=0.001))
    stack.door.limiter = RateLimiter(capacity=1, refill_per_second=0.001)

    async def scenario():
        async with stack.connector.connect(stack.tokens[ADJ1], "rate") as door:
            door.attempts = 1  # see the error itself rather than the client's retry
            await door.call("whoami")
            try:
                await door.call("whoami")
            except DoorCallError as refused:
                return refused.error

    error = run(scenario())
    assert error.code is DoorErrorCode.RATE_LIMITED and error.retryable and error.retry_after > 0
    assert stack.audit_rows[-1]["reason"] == "rate_limited"


def test_a_short_rate_limit_is_waited_out_and_the_request_succeeds(run) -> None:
    stack = Stack()
    stack.door.limiter = RateLimiter(capacity=2, refill_per_second=40)
    assert run(stack.recommend(APPROVE_CLAIM, ADJ1)).status_code == 200
    assert any(r["reason"] == "rate_limited" for r in stack.audit_rows), "it was limited, then retried"


def test_a_long_rate_limit_comes_back_as_429_with_retry_after(run) -> None:
    stack = Stack()
    stack.door.limiter = RateLimiter(capacity=1, refill_per_second=0.01)
    response = run(stack.recommend(APPROVE_CLAIM, ADJ1))
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert int(response.headers["Retry-After"]) >= 1
    assert stack.brain.calls == []


def test_invalid_argument_is_refused_and_audited_not_crashed(run) -> None:
    stack = Stack()
    _, error = run(_call(stack, ADJ1, "get_claim", claim_id="../../etc/passwd"))
    assert error.code is DoorErrorCode.INVALID_ARGUMENT
    assert stack.audit_rows[-1]["reason"] == "bad_claim_id"


def test_a_read_retries_through_a_transient_failure(run) -> None:
    real = httpx.ASGITransport(app=create_documents_app())
    failures = {"left": 2}

    async def flaky(request):
        if failures["left"]:
            failures["left"] -= 1
            return httpx.Response(503, json={"code": "UPSTREAM_UNAVAILABLE"})
        return await real.handle_async_request(request)

    stack = Stack(transports={"documents": httpx.MockTransport(flaky)})
    documents, error = run(_call(stack, ADJ1, "get_claim_documents", claim_id=APPROVE_CLAIM))
    assert error is None and documents
    assert failures["left"] == 0


@pytest.mark.parametrize("exc", [httpx.ConnectError("down"), None])
def test_a_system_that_stays_down_is_upstream_unavailable(run, exc) -> None:
    def down(_request):
        if exc:
            raise exc
        return httpx.Response(503, json={"code": "UPSTREAM_UNAVAILABLE"})

    stack = Stack(transports={"documents": httpx.MockTransport(down)})
    _, error = run(_call(stack, ADJ1, "get_claim_documents", claim_id=APPROVE_CLAIM))
    assert error.code is DoorErrorCode.UPSTREAM_UNAVAILABLE and error.retryable
    # The client retried a retryable error, and each attempt left its own row.
    rows = [r for r in stack.audit_rows if r["action"] == "get_claim_documents"]
    assert len(rows) == 3 and all(r["reason"].startswith("upstream_unavailable") for r in rows)
