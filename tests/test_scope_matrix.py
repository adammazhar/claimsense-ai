"""The scope matrix: role x claim line x assignment x SIU referral -> allow or deny (D-034).

First the pure gate, exhaustively. Then the same matrix end to end, through the MCP door, for every
seat in the roster against real claims, so the gate the tests check is the gate that runs.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime

import pytest

from claimsense.contracts import ClaimAssignment, ClaimLine, DoorErrorCode, Role
from claimsense.door import Identity, authorize, redact
from claimsense.door.scope import SCOPES, scope_of
from claimsense.door_client import DoorCallError
from conftest import ADJ1, ADJ_BI, CUSTOMER_SERVICE, SIU, SIU_CLAIM, SUPERVISOR, Stack

PD, BI = ClaimLine.PHYSICAL_DAMAGE, ClaimLine.BODILY_INJURY
ME, SOMEONE_ELSE = "adj-100", "adj-200"


def assignment(line: ClaimLine, assignee: str, siu: bool) -> ClaimAssignment:
    return ClaimAssignment(claim_id="CLM-2026-0100", adjuster_user_id=assignee, desk="X",
                           assigned_at=datetime(2026, 6, 1, tzinfo=UTC), claim_line=line, siu_referred=siu)


def expected(role: str, line: ClaimLine, mine: bool, siu: bool) -> bool:
    """The matrix as the access-control doc states it (docs/engagement/access-control.md)."""
    return {
        "adjuster_pd": line is PD and mine,
        "adjuster_bi": line is BI and mine,
        "siu": siu,
        "supervisor": True,
    }.get(role, False)


ROLES = [r.value for r in Role] + ["customer_service", "none", ""]


@pytest.mark.parametrize(("role", "line", "mine", "siu"),
                         list(itertools.product(ROLES, [PD, BI], [True, False], [True, False])))
def test_the_gate_matches_the_matrix(role, line, mine, siu) -> None:
    identity = Identity(user_id=ME, role=role, scope=scope_of(role))
    decision = authorize(identity, assignment(line, ME if mine else SOMEONE_ELSE, siu))
    assert decision.allowed is expected(role, line, mine, siu)
    if not decision.allowed:
        assert decision.code is DoorErrorCode.FORBIDDEN_SCOPE


@pytest.mark.parametrize("role", ROLES)
def test_a_missing_claim_is_indistinguishable_except_to_a_supervisor(role) -> None:
    decision = authorize(Identity(ME, role, scope_of(role)), None)
    assert not decision.allowed
    assert decision.code is (DoorErrorCode.NOT_FOUND if role == "supervisor" else DoorErrorCode.FORBIDDEN_SCOPE)


def test_deny_by_default_every_scope_is_named() -> None:
    assert set(SCOPES) == set(Role)
    assert scope_of("customer_service") is None and scope_of("admin") is None


@pytest.mark.parametrize(("role", "sees"), [("adjuster_pd", False), ("adjuster_bi", False), ("siu", True),
                                            ("supervisor", True), ("customer_service", False)])
def test_fraud_details_are_stripped_by_role(role, sees) -> None:
    record = {"claim_id": "CLM-2026-0100", "siu_referral": {"reason": "x"}}
    assert ("siu_referral" in redact(record, Identity(ME, role, scope_of(role)))) is sees


# ---------------------------------------------------------------- the same matrix, through the door
CLAIMS = {"CLM-2026-0001": "pd, adj-001", "CLM-2026-0011": "bi, adj-004", SIU_CLAIM: "pd, adj-003, SIU"}
THROUGH_THE_DOOR = {  # seat -> claims it may read
    ADJ1: {"CLM-2026-0001"},
    ADJ_BI: {"CLM-2026-0011"},
    "adj-003": {SIU_CLAIM},
    SIU: {SIU_CLAIM},
    SUPERVISOR: set(CLAIMS),
    CUSTOMER_SERVICE: set(),
}


def test_every_seat_against_real_claims_through_the_door(run) -> None:
    stack = Stack()

    async def scenario():
        seen: dict[str, set[str]] = {}
        for seat in THROUGH_THE_DOOR:
            async with stack.connector.connect(stack.tokens[seat], f"matrix-{seat}") as door:
                for claim_id in CLAIMS:
                    try:
                        record = await door.call("get_claim", claim_id=claim_id)
                    except DoorCallError as refused:
                        assert refused.error.code is DoorErrorCode.FORBIDDEN_SCOPE
                        continue
                    seen.setdefault(seat, set()).add(claim_id)
                    if claim_id == SIU_CLAIM:
                        assert ("siu_referral" in record) is (seat in (SIU, SUPERVISOR))
        return seen

    seen = run(scenario())
    assert {seat: seen.get(seat, set()) for seat in THROUGH_THE_DOOR} == THROUGH_THE_DOOR
    rows = stack.audit_rows
    assert len(rows) == len(THROUGH_THE_DOOR) * len(CLAIMS)  # one row per call, allow or deny
    assert sum(r["decision"] == "allow" for r in rows) == sum(len(v) for v in THROUGH_THE_DOOR.values())
