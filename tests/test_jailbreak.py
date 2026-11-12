"""Prompt instructions are advisory. A jailbroken agent that reaches for another claim is stopped by the
door's gate in code, and the denial is audited (D-035).

The mock brain's foreign_search fault plays the jailbroken model: whatever its instructions say, its
first move is a search_clauses call on a claim outside the adjuster's scope.
"""

from __future__ import annotations

import pytest

from claimsense.mock_brain import Fault, MockBrain
from claimsense.settings import CLAIM_ASSESSMENT, COVERAGE_CHECK
from conftest import ADJ1, APPROVE_CLAIM, Stack

OUT_OF_SCOPE = "CLM-2026-0011"  # a bodily-injury claim, outside adj-001's physical-damage seat


@pytest.mark.parametrize("stage", [COVERAGE_CHECK, CLAIM_ASSESSMENT])
def test_a_jailbroken_agent_is_refused_by_the_gate_and_audited(run, stage) -> None:
    stack = Stack(MockBrain(fault=Fault("foreign_search", stage, target=OUT_OF_SCOPE)))
    response = run(stack.recommend(APPROVE_CLAIM, ADJ1, correlation_id="jailbreak"))

    rows = [r for r in stack.audit_rows if r["correlation_id"] == "jailbreak"]
    denied = [r for r in rows if r["decision"] == "deny"]
    assert len(denied) == 1
    assert (denied[0]["acting_identity"], denied[0]["action"], denied[0]["resource"], denied[0]["reason"]) == (
        ADJ1, "search_clauses", f"claim/{OUT_OF_SCOPE}", "claim_line_bodily_injury_outside_scope")
    # The model got a refusal, not the other claim: the run carries on for the adjuster's own claim.
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "APPROVE" and body["verdict_source"] == "model"
    assert OUT_OF_SCOPE not in response.text
    assert all(r["resource"] == f"claim/{APPROVE_CLAIM}" for r in rows if r["decision"] == "allow"
               and r["action"] != "whoami")


def test_a_jailbroken_request_cannot_borrow_identity_through_arguments(run) -> None:
    """There is no identity argument to forge: an extra argument is simply not part of the tool."""
    stack = Stack()

    async def scenario():
        async with stack.connector.connect(stack.tokens[ADJ1], "forge") as door:
            result = await door.server.call_tool("get_claim", {"claim_id": OUT_OF_SCOPE, "user_id": "sup-001",
                                                               "role": "supervisor"})
            return result

    result = run(scenario())
    assert result.is_error and '"forbidden_scope"' in result.content[0].text
    row = stack.audit_rows[-1]
    assert (row["acting_identity"], row["role"], row["action"], row["decision"]) == (
        ADJ1, "adjuster_pd", "get_claim", "deny"), "the forged arguments changed nothing: the token decides"
