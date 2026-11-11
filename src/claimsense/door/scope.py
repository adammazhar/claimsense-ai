"""The scope gate: a pure function from (identity, claim routing metadata) to allow or deny (D-034).

Deterministic code, never a prompt. Deny by default: a role not listed here has no scope, and a
claim the gate can't place is refused. A refusal says nothing about whether the claim exists, except
to a supervisor, whose scope is every claim.

    adjuster_pd  physical-damage claims assigned to the seat
    adjuster_bi  bodily-injury claims assigned to the seat
    siu          claims with an open SIU referral
    supervisor   every claim

Fraud details (the SIU referral) are stripped for every role but SIU and supervisor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..contracts import ClaimAssignment, ClaimLine, DoorErrorCode, Role

if TYPE_CHECKING:
    from .identity import Identity

SCOPES: dict[Role, str] = {
    Role.ADJUSTER_PD: "claims:physical_damage:assigned",
    Role.ADJUSTER_BI: "claims:bodily_injury:assigned",
    Role.SIU: "claims:siu_referred",
    Role.SUPERVISOR: "claims:all",
}
LINE_OF: dict[Role, ClaimLine] = {Role.ADJUSTER_PD: ClaimLine.PHYSICAL_DAMAGE,
                                  Role.ADJUSTER_BI: ClaimLine.BODILY_INJURY}
FRAUD_DETAIL_ROLES = frozenset({Role.SIU, Role.SUPERVISOR})
FRAUD_DETAIL_FIELDS = ("siu_referral",)


def scope_of(role: str) -> str | None:
    try:
        return SCOPES[Role(role)]
    except ValueError:
        return None


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    code: DoorErrorCode | None = None  # the error to return on a deny

    @classmethod
    def allow(cls, reason: str) -> Decision:
        return cls(True, reason)

    @classmethod
    def deny(cls, reason: str, code: DoorErrorCode = DoorErrorCode.FORBIDDEN_SCOPE) -> Decision:
        return cls(False, reason, code)


def authorize(identity: Identity, assignment: ClaimAssignment | None) -> Decision:
    """May this identity act on this claim? `assignment` is None when the claim doesn't exist."""
    role = identity.known_role
    if role is None:
        return Decision.deny("role_has_no_scope")
    if assignment is None:
        # Only a seat that could see every claim learns that one doesn't exist (EV-019).
        if role is Role.SUPERVISOR:
            return Decision.deny("no_such_claim", DoorErrorCode.NOT_FOUND)
        return Decision.deny("no_such_claim")
    if role is Role.SUPERVISOR:
        return Decision.allow("supervisor_all_claims")
    if role is Role.SIU:
        return Decision.allow("siu_referred") if assignment.siu_referred else Decision.deny("not_siu_referred")
    if assignment.claim_line is not LINE_OF[role]:
        return Decision.deny(f"claim_line_{assignment.claim_line.value}_outside_scope")
    if assignment.adjuster_user_id != identity.user_id:
        return Decision.deny("not_assigned")
    return Decision.allow("assigned_in_line")


def redact(record: dict, identity: Identity) -> dict:
    """Strip fraud details unless the role may see them. Applied on top of the CMS's own filter."""
    if identity.known_role in FRAUD_DETAIL_ROLES:
        return record
    return {k: v for k, v in record.items() if k not in FRAUD_DETAIL_FIELDS}
