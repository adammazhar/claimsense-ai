"""The two-adjuster test, in process (scripts/two_adjuster_test.py runs it against the compose stack).

Same question, same agent, two identities: a correctly filtered answer to one, a 403 with a structured
error to the other, and two matching audit rows (W16 p.14, brief Milestone 4).
"""

from __future__ import annotations

from conftest import ADJ1, ADJ_BI, FLAG_CLAIM, Stack


def test_same_question_two_scopes(run) -> None:
    stack = Stack()

    async def scenario():
        bi = await stack.recommend(FLAG_CLAIM, ADJ_BI, correlation_id="two-adjuster-bi")
        pd = await stack.recommend(FLAG_CLAIM, ADJ1, correlation_id="two-adjuster-pd")
        return bi, pd

    bi, pd = run(scenario())

    # The BI adjuster gets the co-pilot's real answer for the claim.
    assert bi.status_code == 200
    answer = bi.json()
    assert (answer["claim_id"], answer["verdict_source"], answer["fallback_reason"]) == (FLAG_CLAIM, "model", None)
    assert answer["outcome"] == "FLAG" and answer["status"] == "draft"
    assert "siu_referral" not in bi.text and "claim_line" not in bi.text

    # The PD adjuster gets a 403 with the door's structured error, and nothing about the claim.
    assert pd.status_code == 403
    error = pd.json()["error"]
    assert (error["code"], error["retryable"], error["correlation_id"]) == ("forbidden_scope", False, "two-adjuster-pd")
    assert "Synthetic" not in pd.text and "narrative" not in pd.text

    # Two matching audit rows: the same action on the same resource, allow for one seat, deny for the other.
    allow = next(r for r in stack.audit_rows if r["correlation_id"] == "two-adjuster-bi" and r["action"] == "get_claim")
    deny_rows = [r for r in stack.audit_rows if r["correlation_id"] == "two-adjuster-pd"]
    assert len(deny_rows) == 1, "a refused request leaves exactly one row: the denial"
    deny = deny_rows[0]
    for row, seat, role, decision in ((allow, ADJ_BI, "adjuster_bi", "allow"), (deny, ADJ1, "adjuster_pd", "deny")):
        assert (row["acting_identity"], row["role"], row["action"], row["resource"], row["decision"]) == (
            seat, role, "get_claim", f"claim/{FLAG_CLAIM}", decision)
    assert deny["request_id"] == error["request_id"]
    assert stack.brain.calls.count("document_intake") == 1, "agents ran once: for the BI adjuster only"
