"""The CMS's row filter: the data-layer check under the door's gate (D-035).

The closest our mock systems get to database row-level security. It holds even with the gate
removed, so one layer failing open doesn't expose a claim.
"""

from __future__ import annotations

import pytest

from claimsense.clients import ACTING_ROLE, ACTING_USER
from claimsense.contracts import DoorErrorCode
from claimsense.door import Decision
from claimsense.door_client import DoorCallError
from conftest import ADJ1, ADJ_BI, FLAG_CLAIM, SIU_CLAIM, Stack


def _get(stack: Stack, claim_id: str, user: str | None, role: str | None):
    headers = {ACTING_USER: user, ACTING_ROLE: role} if user else {}
    return stack.backends.cms.get(f"/claims/{claim_id}", headers=headers)


@pytest.mark.parametrize(("user", "role", "status"), [
    (None, None, 403),                       # no acting seat: fail closed
    (ADJ1, "adjuster_pd", 403),              # PD seat, BI claim
    ("adj-002", "adjuster_bi", 403),         # BI seat, not the assignee
    (ADJ_BI, "adjuster_bi", 200),
    ("sup-001", "supervisor", 200),
    ("cs-021", "customer_service", 403),
])
def test_the_cms_filters_claim_rows_by_the_acting_seat(run, user, role, status) -> None:
    assert run(_get(Stack(), FLAG_CLAIM, user, role)).status_code == status


def test_the_cms_strips_fraud_details_for_adjusters(run) -> None:
    stack = Stack()
    adjuster = run(_get(stack, SIU_CLAIM, "adj-003", "adjuster_pd")).json()
    siu = run(_get(stack, SIU_CLAIM, "siu-001", "siu")).json()
    assert "siu_referral" not in adjuster
    assert siu["siu_referral"]["source"] == "legacy_rule"


def test_the_cms_refuses_a_draft_write_outside_the_seat(run) -> None:
    from test_contracts import draft
    stack = Stack()
    body = draft()
    response = run(stack.backends.cms.post(
        f"/claims/{body['claim_id']}/recommendations", json=body,
        headers={"Idempotency-Key": f"{body['claim_id']}:{body['run_id']}", ACTING_USER: ADJ_BI,
                 ACTING_ROLE: "adjuster_bi"}))
    assert response.status_code == 403


def test_with_the_gate_removed_the_cms_still_refuses(run, monkeypatch) -> None:
    """Defense in depth: replace the door's gate with one that allows everything."""
    monkeypatch.setattr("claimsense.door.server.authorize", lambda identity, assignment: Decision.allow("broken"))
    stack = Stack()

    async def scenario():
        async with stack.connector.connect(stack.tokens[ADJ1], "gate-removed") as door:
            try:
                await door.call("get_claim", claim_id=FLAG_CLAIM)
            except DoorCallError as refused:
                return refused.error
        return None

    error = run(scenario())
    assert error is not None and error.code is DoorErrorCode.FORBIDDEN_SCOPE
    row = stack.audit_rows[-1]
    assert (row["decision"], row["reason"], row["resource"]) == ("deny", "cms_row_filter", f"claim/{FLAG_CLAIM}")
