"""The eval checker passes on the committed cases and catches the mistakes it exists to catch."""

from __future__ import annotations

import collections
from pathlib import Path

import yaml

import check_eval_cases

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "evals" / "cases_v0.yaml"


def test_eval_checker_passes() -> None:
    assert check_eval_cases.main(str(CASES)) == 0


def test_five_cases_per_outcome_plus_refusals() -> None:
    """At least five per outcome (the brief); EV-023 and EV-024 add a sixth APPROVE and ROUTE (D-027)."""
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]
    counts = collections.Counter(c["expected"]["outcome"] for c in cases)
    assert counts == {"APPROVE": 6, "DENY": 5, "FLAG": 5, "ROUTE": 6, "REFUSED": 2}


def test_unquoted_comma_in_a_summary_is_caught(tmp_path: Path) -> None:
    text = CASES.read_text(encoding="utf-8").replace(
        'summary: "Tire, rim and alignment, total 2,400."}', "summary: Tire, rim and alignment, total 2,400.}")
    broken = tmp_path / "cases.yaml"
    broken.write_text(text, encoding="utf-8")
    assert check_eval_cases.main(str(broken)) == 1


def test_reasoning_must_be_one_sentence(tmp_path: Path) -> None:
    data = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    data["cases"][0]["expected"]["expected_reasoning"] = "It is covered. It is approved."
    broken = tmp_path / "cases.yaml"
    broken.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert check_eval_cases.main(str(broken)) == 1
