"""The one write, through the door: an idempotency key on every write, and a replay returns the original."""

from __future__ import annotations

from uuid import uuid4

from claimsense.contracts import DoorErrorCode
from claimsense.contracts.idempotency import idempotency_key
from claimsense.door_client import DoorCallError
from conftest import ADJ1, ADJ_BI, APPROVE_CLAIM, Stack
from test_contracts import draft


async def _write(stack: Stack, seat: str, body: dict, key: str | None = None):
    async with stack.connector.connect(stack.tokens[seat], "write") as door:
        try:
            return await door.call("submit_draft_recommendation", claim_id=body["claim_id"],
                                   idempotency_key=key or idempotency_key(body["claim_id"], body["run_id"]),
                                   draft=body), None
        except DoorCallError as refused:
            return None, refused.error


def test_a_replay_returns_the_original(run) -> None:
    stack = Stack()
    body = draft()
    first, _ = run(_write(stack, ADJ1, body))
    replay, _ = run(_write(stack, ADJ1, body))
    assert first["idempotent_replay"] is False and replay["idempotent_replay"] is True
    assert first["recommendation"] == replay["recommendation"]
    assert len(run(stack.drafts(APPROVE_CLAIM))) == 1


def test_the_same_key_with_a_different_draft_is_a_conflict(run) -> None:
    stack = Stack()
    body = draft()
    run(_write(stack, ADJ1, body))
    _, error = run(_write(stack, ADJ1, body | {"outcome": "FLAG"}))
    assert error.code is DoorErrorCode.IDEMPOTENCY_CONFLICT and not error.retryable
    assert [d["outcome"] for d in run(stack.drafts(APPROVE_CLAIM))] == ["APPROVE"]


def test_a_key_that_is_not_claim_and_run_is_refused(run) -> None:
    stack = Stack()
    body = draft()
    _, error = run(_write(stack, ADJ1, body, key=idempotency_key(body["claim_id"], uuid4())))
    assert error.code is DoorErrorCode.INVALID_ARGUMENT


def test_a_draft_must_name_the_acting_seat(run) -> None:
    stack = Stack()
    _, error = run(_write(stack, ADJ1, draft() | {"requested_by": "adj-002"}))
    assert error.code is DoorErrorCode.INVALID_ARGUMENT
    assert stack.audit_rows[-1]["reason"] == "requested_by_not_acting_seat"


def test_a_seat_cannot_write_outside_its_scope(run) -> None:
    stack = Stack()
    _, error = run(_write(stack, ADJ_BI, draft() | {"requested_by": ADJ_BI}))
    assert error.code is DoorErrorCode.FORBIDDEN_SCOPE
    assert run(stack.drafts(APPROVE_CLAIM)) == []


def test_the_write_tool_is_never_offered_to_a_model(run, monkeypatch) -> None:
    """Every tool any agent was handed during a full run: only search_clauses."""
    from claimsense import mock_brain
    offered: set[str] = set()
    original = mock_brain.MockModel.get_response

    async def capture(self, system_instructions, input, model_settings, tools, *args, **kwargs):
        offered.update(t.name for t in tools)
        return await original(self, system_instructions, input, model_settings, tools, *args, **kwargs)

    monkeypatch.setattr(mock_brain.MockModel, "get_response", capture)
    assert run(Stack().recommend(APPROVE_CLAIM, ADJ1)).status_code == 200
    assert offered == {"search_clauses"}
