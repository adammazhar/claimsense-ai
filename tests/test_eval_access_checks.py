"""The eval checker's Milestone 4 rules: seats, claim lines, SIU referrals and the scope matrix (D-038)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import check_eval_cases

CASES = Path(__file__).resolve().parent.parent / "evals" / "cases_v0.yaml"


def _broken(tmp_path: Path, change) -> int:
    data = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    change({c["id"]: c for c in data["cases"]}, data)
    path = tmp_path / "cases.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return check_eval_cases.main(str(path))


@pytest.mark.parametrize("change", [
    lambda c, d: c["EV-011"]["claim"].pop("claim_line"),                       # no claim line
    lambda c, d: c["EV-011"]["claim"].update(claim_line="physical_damage"),    # BI seat on a PD claim
    lambda c, d: c["EV-025"]["requester"].update(role="supervisor"),           # a refusal the matrix allows
    lambda c, d: c["EV-001"]["requester"].update(role="adjuster"),             # not a seat role
    lambda c, d: c["EV-025"]["expected"]["audit"].update(decision="denied"),   # not the door's row shape
    lambda c, d: c["EV-016"]["claim"]["siu_referral"].pop("source"),           # malformed referral
    lambda c, d: d["staff"].append({"user_id": "adj-004", "role": "supervisor"}),  # two roles for one seat
])
def test_the_checker_catches_access_mistakes(tmp_path, change) -> None:
    assert _broken(tmp_path, change) == 1


def test_the_committed_cases_pass_the_scope_matrix(capsys) -> None:
    assert check_eval_cases.main(str(CASES)) == 0
    assert "scope matrix: 22 requests allowed, 3 denied" in capsys.readouterr().out
