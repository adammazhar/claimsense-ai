"""Contracts for the co-pilot's own API: POST /v1/claims/{claim_id}/recommendation.

The response keeps three things apart so a reader can always tell who said what (brief, acceptance
criterion 3): `deterministic` is computed in code, `judgment` comes from the model, and
`code_overrides` records every place code changed what the model drafted.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from .cms import Confidence, DeterministicFacts, Finding, Outcome, RecommendationStatus, VerdictSource
from .common import ClaimId, ClauseId, Contract, DocumentId


class RecommendRequest(Contract):
    """Body of the co-pilot request. A retry that sends the same run_id gets the original result."""

    note: str | None = Field(default=None, max_length=2000, description="Untrusted free text from the requester.")
    run_id: UUID | None = None


class FallbackReason(StrEnum):
    MODEL_UNAVAILABLE = "model_unavailable"
    TIMEOUT = "timeout"
    INVALID_OUTPUT = "invalid_output"
    OUTPUT_SCAN_FAILED = "output_scan_failed"


class CoverageReading(StrEnum):
    COVERED = "covered"
    DOES_NOT_RESPOND = "does_not_respond"
    CANNOT_DETERMINE = "cannot_determine"


class CodeOverride(Contract):
    """A place where deterministic code changed the outcome the model drafted."""

    from_outcome: Outcome
    to_outcome: Outcome
    rule: str


class InjectionFlag(Contract):
    """Instruction-like text that code found in untrusted input. It is evidence, never a command."""

    source: str = Field(description="A document ID, or 'requester_note'.")
    quote: str


class CitedClause(Contract):
    clause_id: ClauseId
    heading: str


class ModelJudgment(Contract):
    """What the model concluded. Absent on a deterministic fallback."""

    model_outcome: Outcome
    coverage_reading: CoverageReading
    coverage_reasoning: str
    fraud_indicated: bool
    injury_exposure: bool
    missing_documents: list[str]
    findings: list[Finding]
    model_ids: list[str] = Field(min_length=1)


class StageUsage(Contract):
    stage: str
    model: str
    requests: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    seconds: float


class RecommendationResponse(Contract):
    run_id: UUID
    claim_id: ClaimId
    status: RecommendationStatus
    outcome: Outcome
    verdict_source: VerdictSource
    fallback_reason: FallbackReason | None = None
    fallback_stage: str | None = None
    fallback_error: str | None = Field(default=None, description="Exception class only; never its message.")
    confidence: Confidence
    reasoning: str
    deterministic: DeterministicFacts
    judgment: ModelJudgment | None = None
    cited_clauses: list[CitedClause]
    evidence_doc_ids: list[DocumentId]
    retrieved_clause_ids: list[ClauseId]
    citations_removed: list[str]
    uncited: bool
    code_overrides: list[CodeOverride]
    injection_flags: list[InjectionFlag]
    recommendation_id: UUID
    usage: list[StageUsage]
    trace_id: str
    correlation_id: str | None = Field(
        default=None, description="Ties this response to the MCP door's audit rows for the request (D-036).")

    @model_validator(mode="after")
    def _source_is_consistent(self) -> RecommendationResponse:
        is_fallback = self.verdict_source is VerdictSource.DETERMINISTIC_FALLBACK
        if is_fallback != (self.fallback_reason is not None):
            raise ValueError("fallback_reason is required for a fallback and forbidden otherwise")
        if is_fallback == (self.judgment is not None):
            raise ValueError("a model verdict carries a judgment; a fallback must not")
        return self
