"""Claims management system (CMS) contracts.

Reads:  GET  /claims/{claim_id}                    -> Claim
        GET  /claims/{claim_id}/assignment         -> ClaimAssignment (source of truth for entitlement)
Write:  POST /claims/{claim_id}/recommendations    -> DraftRecommendationResponse
        (the only write; idempotent on claim_id + run_id, see idempotency.py and D-009)
Event:  AdjusterDecisionEvent, emitted by the CMS when an adjuster confirms or overrides. It is
        what success criterion 3 and the pricing outcome bonus are counted from (D-011).
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, Field, NaiveDatetime, model_validator

from .common import (
    ClaimId,
    ClauseId,
    Contract,
    DocumentId,
    Money,
    PartyId,
    PolicyId,
    Score,
    SyntheticName,
    SyntheticVin,
    UserId,
)


class LossType(StrEnum):
    COLLISION = "collision"
    COMPREHENSIVE = "comprehensive"
    THEFT = "theft"  # a comprehensive peril, kept separate because it has its own document duties


class Vehicle(Contract):
    vin: SyntheticVin
    year: int = Field(ge=1990, le=2027)
    make: str = Field(pattern=r"^Synthetic ")
    model: str


class Party(Contract):
    party_id: PartyId
    display_name: SyntheticName


class GetClaimRequest(Contract):
    """Path parameters for GET /claims/{claim_id} and GET /claims/{claim_id}/assignment."""

    claim_id: ClaimId


class Claim(Contract):
    """The CMS claim record. Response body of GET /claims/{claim_id}."""

    claim_id: ClaimId
    policy_id: PolicyId
    loss_datetime: NaiveDatetime = Field(
        description="Local time at the loss location; the policy-period clause (CLS-PER-006) uses local time."
    )
    loss_type: LossType
    narrative: str = Field(min_length=1)
    vehicle: Vehicle
    claimant: Party
    repair_estimate: Money = Field(description="USD. Zero when there is no estimate (for example, theft).")
    legacy_fraud_score: Score = Field(description="Input to the risk agent only; never the ROUTE trigger (D-007).")
    prior_claims_24m: int = Field(ge=0)
    reported_at: AwareDatetime


class ClaimAssignment(Contract):
    """Response body of GET /claims/{claim_id}/assignment."""

    claim_id: ClaimId
    adjuster_user_id: UserId
    desk: str = Field(min_length=1)
    assigned_at: AwareDatetime


class Outcome(StrEnum):
    """The four decision outcomes, precedence DENY > ROUTE > FLAG > APPROVE (D-002)."""

    APPROVE = "APPROVE"
    DENY = "DENY"
    FLAG = "FLAG"
    ROUTE = "ROUTE"


class VerdictSource(StrEnum):
    """Who produced the outcome. Brief, Milestone 3: model verdicts must be distinguishable."""

    MODEL = "model"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


class DeterministicFacts(Contract):
    """Values computed in code, never by a model (D-001). Shown separately from judgment."""

    in_term: bool
    coverage_present: bool
    total_loss_ratio: float | None = Field(default=None, ge=0)
    total_loss_candidate: bool | None = None
    payable: Money | None = Field(default=None, description="Set only when the outcome is APPROVE.")


class Finding(Contract):
    """One model judgment and the evidence it rests on. Every judgment is cited."""

    statement: str = Field(min_length=1)
    evidence_doc_ids: list[DocumentId] = Field(default_factory=list)
    evidence_clause_ids: list[ClauseId] = Field(default_factory=list)

    @model_validator(mode="after")
    def _must_cite(self) -> Finding:
        if not self.evidence_doc_ids and not self.evidence_clause_ids:
            raise ValueError("a finding must cite at least one document or clause")
        return self


class DraftRecommendationRequest(Contract):
    """Body of POST /claims/{claim_id}/recommendations. Always a draft; never final (EV-014)."""

    claim_id: ClaimId
    run_id: UUID
    outcome: Outcome
    source: VerdictSource
    reasoning: str = Field(min_length=1)
    deterministic: DeterministicFacts
    findings: list[Finding] = Field(min_length=1)
    cited_clause_ids: list[ClauseId] = Field(
        min_length=1, description="Only clause IDs in the retrieved set survive the citation validator (D-005)."
    )
    model_ids: list[str] = Field(default_factory=list, description="Empty when source is deterministic_fallback.")
    requested_by: UserId


class RecommendationStatus(StrEnum):
    DRAFT = "draft"  # the only status the co-pilot can create; the adjuster's action moves it on


class DraftRecommendationResponse(Contract):
    """Response of the write: 201 on first create, 200 with the identical body on replay."""

    recommendation_id: UUID
    claim_id: ClaimId
    run_id: UUID
    status: RecommendationStatus
    created_at: AwareDatetime


class AdjusterAction(StrEnum):
    CONFIRMED = "confirmed"  # outcome, reasoning and citations accepted unchanged
    OVERRIDDEN = "overridden"


class OverrideReason(StrEnum):
    WRONG_OUTCOME = "wrong_outcome"
    WRONG_FACT = "wrong_fact"
    UNSUPPORTED_CITATION = "unsupported_citation"
    MISSING_RISK = "missing_risk"
    OTHER = "other"


class AdjusterDecisionEvent(Contract):
    """Emitted by the CMS (not the co-pilot) when the adjuster acts on a draft."""

    event_id: UUID
    recommendation_id: UUID
    claim_id: ClaimId
    adjuster_user_id: UserId
    action: AdjusterAction
    override_reason: OverrideReason | None = None
    final_outcome: Outcome
    occurred_at: AwareDatetime

    @model_validator(mode="after")
    def _reason_iff_override(self) -> AdjusterDecisionEvent:
        if (self.action is AdjusterAction.OVERRIDDEN) != (self.override_reason is not None):
            raise ValueError("override_reason is required for an override and forbidden for a confirmation")
        return self
