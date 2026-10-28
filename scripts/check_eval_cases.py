"""Check the ClaimSense evaluation cases for structure and internal consistency.

Recomputes every deterministic value (policy term, payable amount, total-loss ratio, days since
inception) from each case's inputs, the same way the production code will, and fails if a
reference label disagrees. Also reports how the legacy fraud-score rule does on the same cases,
which is the baseline the co-pilot has to beat.

Usage:
    python scripts/check_eval_cases.py [evals/cases_v0.yaml]
"""

from __future__ import annotations

import sys
from datetime import date, datetime, time
from pathlib import Path

import yaml

DECISION_OUTCOMES = {"APPROVE", "DENY", "FLAG", "ROUTE"}
REQUIRED_ADVERSARIAL = {"prompt_injection", "cross_record_leakage", "forced_auto_decision"}
PERIOD_START = time(0, 1)  # CLS-PER-006: 12:01 a.m. on the effective and expiration dates
CHECKED_FIELDS = {
    "in_term", "coverage_present", "payable_usd", "tl_ratio",
    "total_loss_candidate", "days_since_inception", "photos_before_inception",
}


def as_date(value: date | str) -> date:
    """Return a date from a YAML date or an ISO string."""
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def as_datetime(value: datetime | str) -> datetime:
    """Return a datetime from a YAML timestamp or an ISO string."""
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def in_term(loss: datetime, effective: date, expiration: date) -> bool:
    """True if the loss falls inside the policy period defined by CLS-PER-006."""
    start = datetime.combine(effective, PERIOD_START)
    end = datetime.combine(expiration, PERIOD_START)
    return start <= loss < end


def coverage_for(loss_type: str) -> str:
    """Map a loss type to the first-party coverage that responds to it."""
    return "collision" if loss_type == "collision" else "comprehensive"


def check_case(case: dict, threshold: float) -> list[str]:
    """Return the problems found in one decision case (empty if it is consistent)."""
    problems: list[str] = []
    claim, policy, expected = case["claim"], case["policy"], case["expected"]
    det = expected.get("deterministic", {})
    loss = as_datetime(claim["loss_datetime"])
    effective = as_date(policy["effective_date"])
    expiration = as_date(policy["expiration_date"])

    term = in_term(loss, effective, expiration)
    if det.get("in_term") != term:
        problems.append(f"in_term should be {term}")

    covered = coverage_for(claim["loss_type"]) in policy.get("coverages", {})
    if det.get("coverage_present") != covered:
        problems.append(f"coverage_present should be {covered}")

    estimate = claim.get("repair_estimate_usd", 0)
    acv = policy.get("vehicle_acv_usd")
    ratio = estimate / acv if acv and estimate else 0.0
    if "tl_ratio" in det and abs(det["tl_ratio"] - ratio) > 0.0051:
        problems.append(f"tl_ratio should be {ratio:.3f}")
    if det.get("total_loss_candidate") is not None and det["total_loss_candidate"] != (ratio >= threshold):
        problems.append("total_loss_candidate disagrees with the threshold")

    if "days_since_inception" in det and det["days_since_inception"] != (loss.date() - effective).days:
        problems.append(f"days_since_inception should be {(loss.date() - effective).days}")

    if "photos_before_inception" in det:
        photos = [d for d in case.get("documents", []) if d.get("type") == "photos" and "captured" in d]
        before = any(as_date(d["captured"]) < effective for d in photos)
        if not photos:
            problems.append("photos_before_inception needs a photos document with a captured date")
        elif det["photos_before_inception"] != before:
            problems.append(f"photos_before_inception should be {before}")

    unchecked = det.keys() - CHECKED_FIELDS
    if unchecked:
        problems.append(f"deterministic fields the checker does not recompute: {sorted(unchecked)}")

    outcome = expected["outcome"]
    if (not term or not covered) and outcome != "DENY":
        problems.append("policy does not respond, so the outcome must be DENY (D-002 precedence)")
    if outcome == "APPROVE":
        if ratio >= threshold:
            problems.append("APPROVE on a total-loss candidate")
        deductible = policy["coverages"][coverage_for(claim["loss_type"])]["deductible_usd"]
        payable = max(min(estimate, acv) - deductible, 0)
        if det.get("payable_usd") != payable:
            problems.append(f"payable_usd should be {payable}")
    if not expected.get("must_cite"):
        problems.append("decision case cites no clause")
    return problems


def main(path: str) -> int:
    """Check every case, print a summary, and return a process exit code."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    cases = data["cases"]
    threshold = data["total_loss_threshold"]
    fraud_cut = data["legacy_fraud_threshold"]
    errors: list[str] = []

    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        errors.append("duplicate case IDs")
    if len(cases) < 20:
        errors.append(f"only {len(cases)} cases; Milestone 1 needs 20")

    counts: dict[str, int] = {}
    families: set[str] = set()
    for case in cases:
        outcome = case["expected"]["outcome"]
        counts[outcome] = counts.get(outcome, 0) + 1
        families |= set(case.get("tags", []))
        if outcome in DECISION_OUTCOMES:
            errors += [f"{case['id']}: {p}" for p in check_case(case, threshold)]
        elif outcome == "REFUSED":
            if case["requester"].get("assigned") is not False:
                errors.append(f"{case['id']}: a refusal case needs an unentitled requester")
            if case["expected"].get("agents_invoked") is not False:
                errors.append(f"{case['id']}: agents must not run on a refused request")
        else:
            errors.append(f"{case['id']}: unknown outcome {outcome}")

    missing = DECISION_OUTCOMES - counts.keys()
    if missing:
        errors.append(f"no cases for outcomes {sorted(missing)}")
    if REQUIRED_ADVERSARIAL - families:
        errors.append(f"no cases for adversarial families {sorted(REQUIRED_ADVERSARIAL - families)}")

    # Baseline: the legacy rule refers a claim when fraud_score >= the cutoff.
    decision_cases = [c for c in cases if c["expected"]["outcome"] in DECISION_OUTCOMES]
    labeled = {c["id"] for c in decision_cases if c["expected"]["outcome"] == "ROUTE"}
    referred = {c["id"] for c in decision_cases if c["claim"]["fraud_score"] >= fraud_cut}
    hits = labeled & referred
    recall = len(hits) / len(labeled) if labeled else 0.0
    precision = len(hits) / len(referred) if referred else 0.0

    adversarial = sum("adversarial" in c.get("tags", []) for c in cases)
    print(f"{len(cases)} cases: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"adversarial cases: {adversarial}; families: {sorted(REQUIRED_ADVERSARIAL & families)}")
    print(
        f"legacy fraud rule (score >= {fraud_cut}) on these cases: "
        f"recall {recall:.0%}, precision {precision:.0%} "
        f"(referred {sorted(referred) or 'none'}; should refer {sorted(labeled)})"
    )
    if errors:
        print("\nPROBLEMS:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\nAll deterministic values and labels are consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "evals/cases_v0.yaml"))
