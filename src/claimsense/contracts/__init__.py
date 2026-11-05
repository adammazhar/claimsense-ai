"""Typed contracts for the three client systems, the clause corpus and the co-pilot API (D-008).

These Pydantic v2 models are the single source of truth: the JSON Schemas in data/schemas/ are
generated from them (scripts/generate_schemas.py) and never edited by hand.
"""

from .cms import (
    AdjusterAction,
    AdjusterDecisionEvent,
    Claim,
    ClaimAssignment,
    Confidence,
    DeterministicFacts,
    DraftRecommendationRequest,
    DraftRecommendationResponse,
    Finding,
    GetClaimRequest,
    LossType,
    Outcome,
    OverrideReason,
    Party,
    RecommendationStatus,
    VerdictSource,
    Vehicle,
)
from .common import Contract, ErrorCode, ErrorResponse
from .copilot import (
    CitedClause,
    CodeOverride,
    CoverageReading,
    FallbackReason,
    InjectionFlag,
    ModelJudgment,
    RecommendationResponse,
    RecommendRequest,
    StageUsage,
)
from .corpus import ClauseEntry, RetrievalHit, RetrievalQuery, RetrievalResult
from .documents import Document, DocumentList, DocumentMeta, DocumentType, GetDocumentRequest, ListDocumentsRequest
from .pas import (
    Coverage,
    CoverageType,
    Endorsement,
    EndorsementType,
    GetPolicyRequest,
    Policy,
    PolicyTransaction,
    StatusField,
    TransactionType,
)

# Models published as JSON Schemas, by file name in data/schemas/.
SCHEMA_MODELS: dict[str, type[Contract]] = {
    "cms.get_claim_request": GetClaimRequest,
    "cms.claim": Claim,
    "cms.claim_assignment": ClaimAssignment,
    "cms.draft_recommendation_request": DraftRecommendationRequest,
    "cms.draft_recommendation_response": DraftRecommendationResponse,
    "cms.adjuster_decision_event": AdjusterDecisionEvent,
    "copilot.recommend_request": RecommendRequest,
    "copilot.recommendation_response": RecommendationResponse,
    "pas.get_policy_request": GetPolicyRequest,
    "pas.policy": Policy,
    "documents.list_documents_request": ListDocumentsRequest,
    "documents.get_document_request": GetDocumentRequest,
    "documents.document_list": DocumentList,
    "documents.document": Document,
    "corpus.clause_entry": ClauseEntry,
    "corpus.retrieval_query": RetrievalQuery,
    "corpus.retrieval_result": RetrievalResult,
    "common.error_response": ErrorResponse,
}

__all__ = [name for name in dir() if not name.startswith("_")]
