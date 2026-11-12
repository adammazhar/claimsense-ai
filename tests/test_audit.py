"""The door's audit trail: a row for every call, a denial on record before its error, append-only (D-036)."""

from __future__ import annotations

import json

from claimsense.door import AuditTrail, verify_file
from claimsense.door.server import Door
from conftest import ADJ1, APPROVE_CLAIM, FLAG_CLAIM, Stack

FIELDS = {"ts", "request_id", "correlation_id", "acting_identity", "role", "scope", "action", "resource", "decision",
          "reason", "prev_hash", "hash"}


def test_every_tool_call_of_a_run_writes_one_row(run) -> None:
    stack = Stack()
    body = run(stack.recommend(APPROVE_CLAIM, ADJ1, correlation_id="one-run")).json()
    rows = [r for r in stack.audit_rows if r["correlation_id"] == "one-run"]
    actions = [r["action"] for r in rows]
    assert actions[:4] == ["get_claim", "whoami", "get_policy", "get_claim_documents"]
    assert actions[-1] == "submit_draft_recommendation"
    assert actions.count("search_clauses") >= 3  # the three seeds, plus any agent searches
    assert all(set(r) == FIELDS and r["decision"] == "allow" and r["acting_identity"] == ADJ1 for r in rows)
    assert body["correlation_id"] == "one-run"


def test_a_denial_is_on_record_before_its_error_is_returned(run, monkeypatch) -> None:
    stack = Stack()
    seen = {}
    original = Door._error

    def checked(code, request_id, correlation_id, message=None, retry_after=None):
        last = stack.door.audit.rows[-1]
        seen["row"] = (last.request_id, last.decision)
        seen["request_id"] = request_id
        return original(code, request_id, correlation_id, message, retry_after)

    monkeypatch.setattr(Door, "_error", staticmethod(checked))
    response = run(stack.recommend(FLAG_CLAIM, ADJ1))
    assert response.status_code == 403
    assert seen["row"] == (seen["request_id"], "deny")


def test_the_trail_on_disk_is_append_only_and_tamper_evident(run, tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    stack = Stack(audit_path=path)
    run(stack.recommend(APPROVE_CLAIM, ADJ1))
    run(stack.recommend(FLAG_CLAIM, ADJ1))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(stack.audit_rows) and verify_file(path) == (True, None)

    tampered = json.loads(lines[1]) | {"decision": "allow" if json.loads(lines[1])["decision"] == "deny" else "deny"}
    path.write_text("\n".join([lines[0], json.dumps(tampered), *lines[2:]]) + "\n", encoding="utf-8")
    assert verify_file(path) == (False, 1)

    path.write_text("\n".join([lines[0], *lines[2:]]) + "\n", encoding="utf-8")  # a row removed
    assert verify_file(path)[0] is False


def test_a_restarted_door_continues_the_chain(run, tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    run(Stack(audit_path=path).recommend(APPROVE_CLAIM, ADJ1))
    run(Stack(audit_path=path).recommend(FLAG_CLAIM, ADJ1))
    assert verify_file(path) == (True, None)


def test_the_writer_has_no_way_to_change_or_remove_a_row() -> None:
    public = {name for name in dir(AuditTrail) if not name.startswith("_")}
    assert public == {"record", "for_correlation"}


def test_no_token_ever_reaches_the_trail_or_the_log(run, tmp_path, caplog) -> None:
    caplog.set_level("DEBUG")
    path = tmp_path / "audit.jsonl"
    stack = Stack(audit_path=path)
    run(stack.recommend(APPROVE_CLAIM, ADJ1))
    run(stack.recommend(FLAG_CLAIM, ADJ1))
    text = path.read_text(encoding="utf-8") + caplog.text
    for token in stack.tokens.values():
        assert token not in text
