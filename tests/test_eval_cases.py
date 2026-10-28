"""The Milestone 1 eval checker still passes on the committed cases."""

from __future__ import annotations

from pathlib import Path

import check_eval_cases

ROOT = Path(__file__).resolve().parent.parent


def test_eval_checker_passes() -> None:
    assert check_eval_cases.main(str(ROOT / "evals" / "cases_v0.yaml")) == 0
