"""Identity comes from the bearer token only: hashed, revocable, expiring, never a tool argument (D-033)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from claimsense.contracts import SeatRegistry
from claimsense.door import RegistryMissing, SeatStore, create_app, hash_token, issue
from claimsense.door.server import Door
from conftest import ADJ1, APPROVE_CLAIM, Stack

ROSTER = [{"user_id": ADJ1, "role": "adjuster_pd"}]


@pytest.mark.parametrize("header", [None, "Bearer", "Basic abc", "Bearer csk_not-a-seat"])
def test_no_valid_token_is_401_and_no_agent_runs(run, header) -> None:
    stack = Stack()
    headers = {"Authorization": header} if header else {}
    response = run(stack.api.post(f"/v1/claims/{APPROVE_CLAIM}/recommendation", headers=headers))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
    assert stack.brain.calls == []


def test_an_unknown_token_is_refused_at_the_transport_and_audited(run) -> None:
    stack = Stack()
    run(stack.api.post(f"/v1/claims/{APPROVE_CLAIM}/recommendation",
                       headers={"Authorization": "Bearer csk_not-a-seat", "X-Correlation-Id": "bad-token"}))
    rows = [r for r in stack.audit_rows if r["correlation_id"] == "bad-token"]
    assert rows and all((r["acting_identity"], r["action"], r["decision"], r["reason"]) ==
                        ("anonymous", "authenticate", "deny", "invalid_token") for r in rows)
    assert not any(r["action"] == "get_claim" for r in rows), "no tool ran"


def test_a_revoked_seat_is_refused_on_the_next_call(run) -> None:
    stack = Stack()
    assert run(stack.recommend(APPROVE_CLAIM, ADJ1)).status_code == 200
    stack.seats.revoke(ADJ1)
    assert run(stack.recommend(APPROVE_CLAIM, ADJ1)).status_code == 401


def test_an_expired_seat_is_refused() -> None:
    registry, tokens = issue(ROSTER, ttl=timedelta(days=1))
    store = SeatStore(registry)
    assert store.resolve(tokens[ADJ1]).user_id == ADJ1
    assert store.resolve(tokens[ADJ1], now=datetime.now(UTC) + timedelta(days=2)) is None


def test_only_hashes_are_stored(tmp_path) -> None:
    registry, tokens = issue(ROSTER)
    text = registry.model_dump_json()
    assert tokens[ADJ1] not in text and hash_token(tokens[ADJ1]) in text


def test_a_revocation_in_the_registry_file_takes_effect_without_a_restart(tmp_path) -> None:
    registry, tokens = issue(ROSTER)
    path = tmp_path / "seats.json"
    path.write_text(registry.model_dump_json(), encoding="utf-8")
    store = SeatStore(path=path)
    assert store.resolve(tokens[ADJ1]) is not None
    revoked = SeatRegistry(seats=[s.model_copy(update={"revoked_at": datetime.now(UTC)}) for s in registry.seats])
    path.write_text(revoked.model_dump_json(), encoding="utf-8")
    import os
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1_000_000))
    assert store.resolve(tokens[ADJ1]) is None


def test_the_door_fails_closed_without_a_registry(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SEAT_REGISTRY", str(tmp_path / "missing.json"))
    with pytest.raises(RegistryMissing, match="issue_seat_tokens.py"):
        create_app(Door.from_env())


def test_no_door_tool_takes_an_identity_argument(run) -> None:
    stack = Stack()
    mcp, _ = stack.door.build()

    async def schemas():
        return {t.name: json.dumps(t.input_schema) for t in await mcp.list_tools()}

    for name, schema in run(schemas()).items():
        for word in ("user", "role", "scope", "identity", "token", "seat"):
            assert f'"{word}' not in schema, (name, word)
