"""Citations must come from what was retrieved for this claim (D-005, D-019)."""

from __future__ import annotations

from claimsense.guardrails import validate_citations
from claimsense.mock_brain import Fault, MockBrain
from claimsense.settings import COVERAGE_CHECK, DECISION_DRAFT
from conftest import APPROVE_CLAIM, DENY_CLAIM, ROUTE_CLAIM, Stack


def test_keeps_retrieved_citations() -> None:
    check = validate_citations(["CLS-COL-001", "CLS-PER-006"], ["CLS-PER-006", "CLS-COL-001", "CLS-DEC-001"])
    assert check.kept == ["CLS-COL-001", "CLS-PER-006"]
    assert check.removed == [] and check.uncited is False


def test_removes_unretrieved_citations_and_marks_uncited() -> None:
    check = validate_citations(["CLS-COL-001", "CLS-XXX-999"], ["CLS-COL-001"])
    assert check.kept == ["CLS-COL-001"]
    assert check.removed == ["CLS-XXX-999"]
    assert check.uncited is True


def test_no_citation_at_all_is_uncited() -> None:
    assert validate_citations([], ["CLS-COL-001"]).uncited is True
    assert validate_citations(["CLS-XXX-999"], []).kept == []


def test_a_real_clause_not_retrieved_for_this_claim_is_still_removed() -> None:
    """Existing in the corpus isn't enough: it has to have been retrieved for this claim."""
    check = validate_citations(["CLS-FRD-001"], ["CLS-COL-001"])
    assert check.removed == ["CLS-FRD-001"] and check.uncited is True


def test_duplicates_collapse() -> None:
    check = validate_citations(["CLS-COL-001", "CLS-COL-001"], ["CLS-COL-001"])
    assert check.kept == ["CLS-COL-001"]


def test_invented_citation_never_reaches_the_response_or_the_cms(run) -> None:
    async def scenario():
        stack = Stack(MockBrain(fault=Fault("invent_citation", COVERAGE_CHECK)))
        response = (await stack.recommend(APPROVE_CLAIM)).json()
        return response, await stack.drafts(APPROVE_CLAIM)

    response, drafts = run(scenario())
    cited = [c["clause_id"] for c in response["cited_clauses"]]
    assert "CLS-XXX-999" not in cited
    assert "CLS-XXX-999" not in drafts[0]["cited_clause_ids"]
    assert response["citations_removed"] == ["CLS-XXX-999"]
    assert response["uncited"] is True and drafts[0]["uncited"] is True
    assert set(cited) <= set(response["retrieved_clause_ids"])


def test_uncited_approval_goes_to_an_adjuster_and_stays_labeled_model(run) -> None:
    """The model drafted APPROVE on an invented clause: code blocks it, and says it did."""
    response = run(Stack(MockBrain(fault=Fault("invent_citation", DECISION_DRAFT))).recommend(APPROVE_CLAIM)).json()
    assert response["outcome"] == "FLAG"
    assert response["judgment"]["model_outcome"] == "APPROVE"
    assert response["verdict_source"] == "model"
    assert response["deterministic"]["payable"] is None
    override = response["code_overrides"][0]
    assert (override["from_outcome"], override["to_outcome"]) == ("APPROVE", "FLAG")


def test_a_code_computed_denial_survives_an_invented_citation(run) -> None:
    response = run(Stack(MockBrain(fault=Fault("invent_citation", DECISION_DRAFT))).recommend(DENY_CLAIM)).json()
    assert response["outcome"] == "DENY" and response["uncited"] is True


def test_an_invented_citation_does_not_cancel_a_fraud_referral(run) -> None:
    response = run(Stack(MockBrain(fault=Fault("invent_citation", DECISION_DRAFT))).recommend(ROUTE_CLAIM)).json()
    assert response["outcome"] == "ROUTE" and response["uncited"] is True
