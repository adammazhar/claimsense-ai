"""The contracts reject what the boundary must reject, and the published schemas match the models."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

import generate_schemas
from claimsense.contracts import (
    AdjusterDecisionEvent,
    Claim,
    DraftRecommendationRequest,
    Finding,
    Policy,
    RetrievalResult,
)
from test_fixtures import load


def draft(**overrides) -> dict:
    body = {
        "claim_id": "CLM-2026-0001", "run_id": str(uuid4()), "outcome": "APPROVE", "verdict_source": "model", "confidence": "high", "uncited": False,
        "reasoning": "Pothole damage consistent with the estimate and photos.",
        "deterministic": {"in_term": True, "coverage_present": True, "total_loss_ratio": 0.13, "payable": "1900.00"},
        "findings": [{"statement": "Damage matches the narrative.", "evidence_doc_ids": ["DOC-0001-2"]}],
        "cited_clause_ids": ["CLS-COL-001"], "model_ids": ["placeholder-model"], "requested_by": "adj-001",
    }
    return body | overrides


def test_published_schemas_are_up_to_date() -> None:
    assert generate_schemas.main(["--check"]) == 0, "run scripts/generate_schemas.py"


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Claim.model_validate(load("claims")[0] | {"ssn": "000-00-0000"})


def test_real_looking_vin_and_name_are_rejected() -> None:
    claim = load("claims")[0]
    with pytest.raises(ValidationError):
        Claim.model_validate(claim | {"vehicle": claim["vehicle"] | {"vin": "1HGCM82633A004352"}})
    with pytest.raises(ValidationError):
        Claim.model_validate(claim | {"claimant": claim["claimant"] | {"display_name": "Jane Smith"}})


def test_money_is_exact_and_never_negative() -> None:
    claim = load("claims")[0]
    assert Claim.model_validate(claim).model_dump(mode="json")["repair_estimate"] == "2400.00"
    with pytest.raises(ValidationError):
        Claim.model_validate(claim | {"repair_estimate": "-1"})
    with pytest.raises(ValidationError):
        Claim.model_validate(claim | {"repair_estimate": "10.005"})


def test_policy_term_must_be_ordered() -> None:
    policy = load("policies")[0]
    with pytest.raises(ValidationError):
        Policy.model_validate(policy | {"expiration_date": policy["effective_date"]})


def test_a_finding_must_cite_evidence() -> None:
    with pytest.raises(ValidationError):
        Finding(statement="Looks fine.")


def test_draft_cannot_be_final_and_must_cite() -> None:
    DraftRecommendationRequest.model_validate(draft())
    with pytest.raises(ValidationError):
        DraftRecommendationRequest.model_validate(draft(status="final"))
    with pytest.raises(ValidationError):
        DraftRecommendationRequest.model_validate(draft(cited_clause_ids=[]))
    DraftRecommendationRequest.model_validate(draft(cited_clause_ids=[], uncited=True))


def test_fallback_cannot_name_a_model() -> None:
    with pytest.raises(ValidationError):
        DraftRecommendationRequest.model_validate(draft(verdict_source="deterministic_fallback"))
    DraftRecommendationRequest.model_validate(draft(verdict_source="deterministic_fallback", model_ids=[]))


def test_override_requires_a_reason() -> None:
    event = {"event_id": str(uuid4()), "recommendation_id": str(uuid4()), "claim_id": "CLM-2026-0001",
             "adjuster_user_id": "adj-001", "action": "overridden", "final_outcome": "FLAG",
             "occurred_at": "2026-11-18T10:00:00Z"}
    with pytest.raises(ValidationError):
        AdjusterDecisionEvent.model_validate(event)
    AdjusterDecisionEvent.model_validate(event | {"override_reason": "missing_risk"})


def test_retrieval_result_exposes_retrieved_ids() -> None:
    result = RetrievalResult.model_validate({
        "query": {"query": "policy period", "form_number": "SYN-PA-01"},
        "hits": [{"clause_id": "CLS-PER-006", "score": 0.9, "heading": "Policy period", "text": "..."}],
    })
    assert result.retrieved_ids() == {"CLS-PER-006"}


def test_schemas_on_disk_are_valid_json() -> None:
    for text in generate_schemas.schemas().values():
        assert json.loads(text)["type"] == "object"
