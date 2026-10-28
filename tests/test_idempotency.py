"""The idempotency rule for POST /claims/{claim_id}/recommendations (D-009)."""

from __future__ import annotations

from uuid import uuid4

from claimsense.contracts import DraftRecommendationRequest, ErrorCode
from claimsense.contracts.idempotency import IdempotencyStore, body_fingerprint, idempotency_key
from test_contracts import draft


def make(**overrides) -> DraftRecommendationRequest:
    return DraftRecommendationRequest.model_validate(draft(**overrides))


def test_first_write_creates_a_draft() -> None:
    store, body = IdempotencyStore(), make()
    result = store.submit(body.claim_id, idempotency_key(body.claim_id, body.run_id), body)
    assert result.status == 201
    assert result.body.status == "draft"
    assert len(store) == 1


def test_replay_returns_the_original_result() -> None:
    store, body = IdempotencyStore(), make()
    key = idempotency_key(body.claim_id, body.run_id)
    first = store.submit(body.claim_id, key, body)
    again = store.submit(body.claim_id, key, make(**body.model_dump(mode="json")))
    assert again.status == 200
    assert again.body == first.body
    assert len(store) == 1


def test_conflicting_body_is_409_and_writes_nothing() -> None:
    store, body = IdempotencyStore(), make()
    key = idempotency_key(body.claim_id, body.run_id)
    first = store.submit(body.claim_id, key, body)
    changed = make(**(body.model_dump(mode="json") | {"outcome": "DENY"}))
    result = store.submit(body.claim_id, key, changed)
    assert result.status == 409
    assert result.body.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert store.submit(body.claim_id, key, body).body == first.body


def test_missing_or_mismatched_key_is_rejected() -> None:
    store, body = IdempotencyStore(), make()
    assert store.submit(body.claim_id, None, body).body.code is ErrorCode.IDEMPOTENCY_KEY_MISSING
    wrong = idempotency_key(body.claim_id, uuid4())
    assert store.submit(body.claim_id, wrong, body).body.code is ErrorCode.IDEMPOTENCY_KEY_MISMATCH
    other_path = store.submit("CLM-2026-0002", idempotency_key(body.claim_id, body.run_id), body)
    assert other_path.body.code is ErrorCode.IDEMPOTENCY_KEY_MISMATCH
    assert len(store) == 0


def test_new_run_id_is_a_new_draft() -> None:
    store, body = IdempotencyStore(), make()
    store.submit(body.claim_id, idempotency_key(body.claim_id, body.run_id), body)
    second = make(run_id=str(uuid4()))
    assert store.submit(second.claim_id, idempotency_key(second.claim_id, second.run_id), second).status == 201
    assert len(store) == 2


def test_fingerprint_ignores_field_order() -> None:
    body = make()
    reordered = DraftRecommendationRequest.model_validate(dict(reversed(list(body.model_dump(mode="json").items()))))
    assert body_fingerprint(body) == body_fingerprint(reordered)
