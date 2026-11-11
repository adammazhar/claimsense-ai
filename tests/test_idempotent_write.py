"""The one write, over HTTP against the mock CMS and through the co-pilot (D-009)."""

from __future__ import annotations

from uuid import uuid4

import httpx

from claimsense.api import create_app
from claimsense.clients import ACTING_ROLE, ACTING_USER
from claimsense.contracts.idempotency import idempotency_key
from claimsense.mock_brain import Fault
from conftest import APPROVE_CLAIM, Stack
from test_contracts import draft


async def _post(stack: Stack, body: dict, key: str | None, claim_id: str = APPROVE_CLAIM):
    headers = {"Idempotency-Key": key} if key else {}
    headers |= {ACTING_USER: "adj-001", ACTING_ROLE: "adjuster_pd"}  # the owner, as the door would pass it
    return await stack.clients.cms.post(f"/claims/{claim_id}/recommendations", json=body, headers=headers)


def test_replay_returns_the_original_and_writes_once(run) -> None:
    async def scenario():
        stack = Stack()
        body = draft()
        key = idempotency_key(body["claim_id"], body["run_id"])
        return await _post(stack, body, key), await _post(stack, body, key), await stack.drafts(APPROVE_CLAIM)

    first, replay, drafts = run(scenario())
    assert (first.status_code, replay.status_code) == (201, 200)
    assert first.json() == replay.json()
    assert len(drafts) == 1


def test_conflicting_body_is_409_and_writes_nothing(run) -> None:
    async def scenario():
        stack = Stack()
        body = draft()
        key = idempotency_key(body["claim_id"], body["run_id"])
        await _post(stack, body, key)
        return await _post(stack, body | {"outcome": "FLAG"}, key), await stack.drafts(APPROVE_CLAIM)

    conflict, drafts = run(scenario())
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert [d["outcome"] for d in drafts] == ["APPROVE"]


def test_missing_or_wrong_key_is_400(run) -> None:
    async def scenario():
        stack = Stack()
        body = draft()
        return (await _post(stack, body, None),
                await _post(stack, body, idempotency_key(body["claim_id"], uuid4())),
                await stack.drafts(APPROVE_CLAIM))

    missing, wrong, drafts = run(scenario())
    assert (missing.status_code, missing.json()["code"]) == (400, "IDEMPOTENCY_KEY_MISSING")
    assert (wrong.status_code, wrong.json()["code"]) == (400, "IDEMPOTENCY_KEY_MISMATCH")
    assert drafts == []


def test_a_body_that_breaks_the_contract_is_422(run) -> None:
    async def scenario():
        stack = Stack()
        body = draft() | {"status": "final"}
        return await _post(stack, body, idempotency_key(body["claim_id"], body["run_id"]))

    response = run(scenario())
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_FAILED")


def test_copilot_retry_with_the_same_run_id_returns_the_original_without_rerunning(run) -> None:
    async def scenario():
        stack = Stack()
        run_id = str(uuid4())
        first = await stack.recommend(APPROVE_CLAIM, run_id=run_id)
        calls = len(stack.brain.calls)
        second = await stack.recommend(APPROVE_CLAIM, run_id=run_id)
        return first, second, calls, len(stack.brain.calls), await stack.drafts(APPROVE_CLAIM)

    first, second, calls_before, calls_after, drafts = run(scenario())
    assert first.json() == second.json()
    assert calls_after == calls_before
    assert len(drafts) == 1


def test_a_retry_cannot_read_someone_elses_result(run) -> None:
    async def scenario():
        stack = Stack()
        run_id = str(uuid4())
        await stack.recommend(APPROVE_CLAIM, run_id=run_id)
        return await stack.recommend(APPROVE_CLAIM, user="adj-007", run_id=run_id)

    assert run(scenario()).status_code == 403


def test_a_changed_result_under_a_used_run_id_is_a_conflict_not_a_second_draft(run) -> None:
    """The co-pilot restarted and lost its cache, then re-ran with a run_id the CMS already holds."""
    async def scenario():
        stack = Stack()
        run_id = str(uuid4())
        await stack.recommend(APPROVE_CLAIM, run_id=run_id)
        stack.api = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(stack.pipeline)),
                                      base_url="http://copilot")
        stack.pipeline.agents.draft.model.fault = Fault("invent_citation")  # the re-run answers differently
        return await stack.recommend(APPROVE_CLAIM, run_id=run_id), await stack.drafts(APPROVE_CLAIM)

    response, drafts = run(scenario())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_conflict"
    assert len(drafts) == 1
