"""The CI workflow can't swallow a failed gate (D-041).

GitHub runs a step with no `shell:` as `bash -e`, without pipefail, so `run_evals.py ... | tee` reported
tee's exit status and a failed live gate went green. The workflow now defaults every step to `bash`,
which GitHub runs as `bash --noprofile --norc -eo pipefail`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_every_step_runs_with_pipefail() -> None:
    workflow = _workflow()
    assert workflow["defaults"]["run"]["shell"] == "bash"
    for name, job in workflow["jobs"].items():
        assert job.get("defaults", {}).get("run", {}).get("shell", "bash") == "bash", name
        for step in job["steps"]:
            assert step.get("shell", "bash") == "bash", (name, step.get("name"))


def test_the_live_gate_still_pipes_the_report_through_tee() -> None:
    """The pipe the bug lived in is still there, so the default above is what protects it."""
    steps = _workflow()["jobs"]["live-eval-gate"]["steps"]
    gate = next(s for s in steps if "run_evals.py --brain openai" in s.get("run", ""))
    assert "| tee" in gate["run"]
