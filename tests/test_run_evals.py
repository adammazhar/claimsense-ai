"""The gate itself: it has to fail when it should. Whether today's labels pass is CI's eval-gate job."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

import run_evals
from claimsense.mock_brain import Fault, MockBrain

CASES = Path(__file__).resolve().parent.parent / "evals" / "cases_v0.yaml"


@pytest.fixture
def cases() -> list[dict]:
    return yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]


def by_id(cases: list[dict], case_id: str) -> dict:
    return next(c for c in cases if c["id"] == case_id)


def test_fallback_verdicts_count_as_misses_and_fail_the_gate(run, cases) -> None:
    report = run(run_evals.evaluate(cases, MockBrain(fault=Fault("unavailable", "document_intake"))))
    summary = report["summary"]
    assert summary["decision_accuracy"] == 0.0
    assert summary["fallback_verdicts"] == summary["decision_cases"]
    assert summary["gate"]["passed"] is False


def test_one_fallback_fails_the_gate_even_above_the_accuracy_floor(run, cases) -> None:
    """Every decision case must be the model's verdict (D-024): one fallback is red even above the floor."""
    results = run(run_evals.evaluate(cases, MockBrain()))["results"]
    one = next(r for r in results if r["id"] == "EV-001")
    one.update(verdict_source="deterministic_fallback", hit=False)
    summary = run_evals.summarize(results, "openai", partial=False)
    assert summary["decision_accuracy"] == (summary["decision_cases"] - 1) / summary["decision_cases"] > 0.85
    assert summary["gate"]["passed"] is False
    assert any("EV-001" in reason and "not decided by the model" in reason for reason in summary["gate"]["reasons"])


def test_the_live_gate_fails_without_a_key_before_any_case_runs(monkeypatch, capsys) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(run_evals, "load_dotenv", lambda: None)
    monkeypatch.setattr(run_evals, "evaluate", lambda *a, **k: pytest.fail("a case ran without a key"))
    assert run_evals.main(["--brain", "openai"]) == 1
    assert "OPENAI_API_KEY is not set" in capsys.readouterr().out


def test_a_report_only_case_file_is_scored_but_never_gated(run, cases) -> None:
    summary = run(run_evals.evaluate(cases, MockBrain(), gated=False))["summary"]
    assert summary["decision_accuracy"] == 1.0
    assert summary["gate"] == {"passed": False, "applies": False, "report_only": True, "reasons": []}


def test_a_wrong_outcome_on_one_adversarial_case_fails_the_gate_even_above_the_accuracy_floor(run, cases) -> None:
    broken = copy.deepcopy(cases)
    by_id(broken, "EV-008")["expected"]["outcome"] = "FLAG"
    summary = run(run_evals.evaluate(broken, MockBrain()))["summary"]
    assert summary["gate"]["passed"] is False
    assert any("adversarial" in reason for reason in summary["gate"]["reasons"])


def test_accuracy_below_the_floor_fails_the_gate(run, cases) -> None:
    broken = copy.deepcopy(cases)
    for case_id in ("EV-001", "EV-002", "EV-003", "EV-005", "EV-006"):
        by_id(broken, case_id)["expected"]["outcome"] = "FLAG"
    summary = run(run_evals.evaluate(broken, MockBrain()))["summary"]
    assert summary["decision_accuracy"] <= 0.80
    assert any("decision accuracy" in reason for reason in summary["gate"]["reasons"])


def test_a_failing_access_control_case_fails_the_gate(run, cases) -> None:
    broken = copy.deepcopy(cases)
    by_id(broken, "EV-020")["requester"]["user_id"] = "adj-001"  # now entitled, so no refusal comes back
    summary = run(run_evals.evaluate(broken, MockBrain()))["summary"]
    assert any("access-control" in reason for reason in summary["gate"]["reasons"])


def test_an_uncited_verdict_is_a_miss_even_when_its_outcome_is_right(run, cases) -> None:
    """EV-015 is a ROUTE: an invented citation leaves the outcome standing but the verdict uncited."""
    report = run(run_evals.evaluate([by_id(cases, "EV-015")], MockBrain(fault=Fault("invent_citation")), partial=True))
    result = report["results"][0]
    assert (result["outcome"], result["verdict_source"], result["uncited"]) == ("ROUTE", "model", True)
    assert result["hit"] is False and result["passed"] is False
    assert any("uncited" in p for p in result["problems"])
    assert report["summary"]["decision_accuracy"] == 0.0


def test_a_partial_run_cannot_pass_the_gate(run, cases) -> None:
    gate = run(run_evals.evaluate([by_id(cases, "EV-001")], MockBrain(), partial=True))["summary"]["gate"]
    assert gate["passed"] is False and gate["applies"] is False


def test_every_must_not_rule_in_the_cases_has_an_evaluator(cases) -> None:
    world = {"claims": {"CLM-2026-0019": {"narrative": "n", "vehicle": {"vin": "v"}, "policy_id": "p",
                                          "claimant": {"display_name": "d"}},
                        "CLM-2026-0001": {"narrative": "n", "vehicle": {"vin": "v"}, "policy_id": "p",
                                          "claimant": {"display_name": "d"}},
                        "CLM-2026-0011": {"narrative": "n", "vehicle": {"vin": "v"}, "policy_id": "p",
                                          "claimant": {"display_name": "d"}}},
             "refusal_for_missing_claim": '{"a": 1}'}
    for case in cases:
        for rule in case["expected"].get("must_not", []):
            problem = run_evals.check_must_not(rule, case, 200, {}, '{"a": 1}', world)
            assert not (problem or "").startswith("no evaluator"), rule


def test_an_unknown_must_not_rule_is_a_failure_not_a_silent_pass(cases) -> None:
    problem = run_evals.check_must_not("A rule nobody wrote code for", cases[0], 200, {}, "{}", {"claims": {}})
    assert problem.startswith("no evaluator")


def test_attributing_an_injected_claim_is_not_asserting_it() -> None:
    assert run_evals._asserted(r"fraud review passed", ["The fraud review passed."])
    assert not run_evals._asserted(r"fraud review passed", ["The letter claims the fraud review passed."])


def test_cost_comes_from_token_counts() -> None:
    results = [{"usage": [{"model": "gpt-4o", "requests": 1, "input_tokens": 1_000_000, "cached_input_tokens": 0,
                           "output_tokens": 100_000}]}]
    assert run_evals.usage_summary(results)["total_cost_usd"] == 3.5
