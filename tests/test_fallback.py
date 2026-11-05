"""A fallback answers when the model can't, and always says it is a fallback (rubric area C)."""

from __future__ import annotations

import pytest

from claimsense.mock_brain import Fault, MockBrain, OpenAIBrain
from claimsense.settings import CLAIM_ASSESSMENT, COVERAGE_CHECK, DECISION_DRAFT, DOCUMENT_INTAKE
from conftest import APPROVE_CLAIM, DENY_CLAIM, ROUTE_CLAIM, Stack

STAGES = [DOCUMENT_INTAKE, COVERAGE_CHECK, CLAIM_ASSESSMENT, DECISION_DRAFT]


def fallback_run(run, claim_id: str, kind: str, stage: str = DECISION_DRAFT) -> dict:
    stack = Stack(MockBrain(fault=Fault(kind, stage)), stage_timeout=0.2)
    return run(stack.recommend(claim_id)).json()


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize(("kind", "reason"), [
    ("unavailable", "model_unavailable"), ("timeout", "timeout"), ("invalid", "invalid_output")])
def test_every_failure_at_every_stage_is_labeled(run, kind: str, reason: str, stage: str) -> None:
    response = fallback_run(run, APPROVE_CLAIM, kind, stage)
    assert response["verdict_source"] == "deterministic_fallback"
    assert response["fallback_reason"] == reason
    assert response["fallback_stage"] == stage
    assert response["judgment"] is None
    assert response["reasoning"].startswith("Deterministic fallback, not a model verdict")


def test_model_verdict_is_labeled_model(run, stack) -> None:
    response = run(stack.recommend(APPROVE_CLAIM)).json()
    assert response["verdict_source"] == "model"
    assert response["fallback_reason"] is None and response["judgment"] is not None


def test_fallback_is_flag_when_only_a_model_could_read_the_file(run) -> None:
    assert fallback_run(run, APPROVE_CLAIM, "unavailable")["outcome"] == "FLAG"


def test_fallback_never_routes_or_approves(run) -> None:
    """Fraud needs reading. A fallback must not pretend it read anything, or approve money."""
    assert fallback_run(run, ROUTE_CLAIM, "unavailable")["outcome"] == "FLAG"
    response = fallback_run(run, APPROVE_CLAIM, "unavailable")
    assert response["outcome"] != "APPROVE" and response["deterministic"]["payable"] is None


def test_fallback_denies_on_the_term_check_and_cites_the_clause(run) -> None:
    response = fallback_run(run, DENY_CLAIM, "unavailable")
    assert response["outcome"] == "DENY"
    assert [c["clause_id"] for c in response["cited_clauses"]] == ["CLS-PER-006"]


def test_fallback_label_lands_in_the_cms(run) -> None:
    async def scenario():
        stack = Stack(MockBrain(fault=Fault("unavailable")))
        await stack.recommend(APPROVE_CLAIM)
        return await stack.drafts(APPROVE_CLAIM)

    draft = run(scenario())[0]
    assert draft["verdict_source"] == "deterministic_fallback"
    assert draft["model_ids"] == []


def test_output_naming_another_claim_falls_back(run) -> None:
    response = fallback_run(run, APPROVE_CLAIM, "foreign_claim")
    assert response["fallback_reason"] == "output_scan_failed"
    assert "CLM-2026-0999" not in str(response)


def test_missing_key_means_model_unavailable_not_a_crash(run, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = run(Stack(OpenAIBrain()).recommend(APPROVE_CLAIM))
    assert response.status_code == 200
    assert response.json()["verdict_source"] == "deterministic_fallback"
    assert response.json()["fallback_reason"] == "model_unavailable"
