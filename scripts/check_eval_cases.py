"""Check the ClaimSense evaluation cases for structure and internal consistency.

Recomputes every deterministic value (policy term, payable amount, total-loss ratio, days since
inception) from each case's inputs, the same way the production code will, and fails if a
reference label disagrees. Also reports how the legacy fraud-score rule does on the same cases,
which is the baseline the co-pilot has to beat.

Usage:
    python scripts/check_eval_cases.py [evals/cases_v0.yaml]
"""

from __future__ import annotations

import re
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
MIN_PER_OUTCOME = 5  # instructor's Week 1 checklist: 5 approve, 5 deny, 5 flag_review, 5 route_specialist
CONFIDENCE_LEVELS = {"high", "medium"}
SPLITS = {"tuning", "heldout"}
DOCUMENT_KEYS = {"doc_id", "type", "summary", "captured"}
# Milestone 4 (D-034, D-038): seat roles, claim lines and the scope matrix, recomputed here independently
# of claimsense.door.scope, the way the deterministic values are.
SEAT_ROLES = {"adjuster_pd", "adjuster_bi", "siu", "supervisor", "customer_service"}
CLAIM_LINES = {"physical_damage", "bodily_injury"}
ADJUSTER_LINE = {"adjuster_pd": "physical_damage", "adjuster_bi": "bodily_injury"}
SIU_REFERRAL_KEYS = {"referred_at", "source", "reason"}
AUDIT_KEYS = {"acting_identity", "action", "resource", "decision"}


def scope_allows(role: str, user: str, claim_line: str | None, assignee: str | None, siu: bool) -> bool:
    """The access-control matrix (docs/engagement/access-control.md). Deny by default."""
    if role == "supervisor":
        return claim_line is not None
    if role == "siu":
        return siu
    line = ADJUSTER_LINE.get(role)
    return line is not None and claim_line == line and assignee == user


def check_access(cases: list[dict], staff: list[dict]) -> tuple[list[str], int, int]:
    """Seats, claim lines, SIU referrals and the refusal audit rows; then the scope matrix on every case.
    Returns (problems, allowed, denied)."""
    problems: list[str] = []
    roles: dict[str, str] = {}
    for entry in [*(c["requester"] for c in cases), *staff]:
        if entry.get("role") not in SEAT_ROLES:
            problems.append(f"{entry.get('user_id')}: unknown seat role {entry.get('role')!r}")
        if roles.setdefault(entry["user_id"], entry.get("role")) != entry.get("role"):
            problems.append(f"{entry['user_id']}: two different seat roles")
    claims: dict[str, dict] = {}
    for case in cases:
        claim = case["claim"]
        if "loss_type" not in claim:
            continue  # a refusal case that reuses another case's claim
        if claim.get("claim_line") not in CLAIM_LINES:
            problems.append(f"{case['id']}: claim_line must be one of {sorted(CLAIM_LINES)}")
        referral = claim.get("siu_referral")
        if referral is not None and set(referral) != SIU_REFERRAL_KEYS:
            problems.append(f"{case['id']}: siu_referral needs exactly {sorted(SIU_REFERRAL_KEYS)}")
        requester = case["requester"]
        assignee = requester["user_id"] if requester.get("assigned") else None
        claims[claim["claim_id"]] = {"line": claim.get("claim_line"), "assignee": assignee, "siu": referral is not None}
    allowed = denied = 0
    for case in cases:
        requester, claim_id = case["requester"], case["claim"]["claim_id"]
        record = claims.get(claim_id, {"line": None, "assignee": None, "siu": False})
        ok = scope_allows(requester.get("role", ""), requester["user_id"], record["line"], record["assignee"],
                          record["siu"])
        allowed, denied = allowed + ok, denied + (not ok)
        refusal = case["expected"]["outcome"] == "REFUSED"
        if refusal and ok:
            problems.append(f"{case['id']}: the scope matrix allows this requester, so it can't be a refusal")
        if not refusal and not ok:
            problems.append(f"{case['id']}: the scope matrix denies this requester its own claim")
        if refusal:
            audit = case["expected"].get("audit", {})
            if set(audit) != AUDIT_KEYS or audit.get("decision") != "deny" or audit.get("action") != "get_claim":
                problems.append(f"{case['id']}: audit must be the door's get_claim deny row: {sorted(AUDIT_KEYS)}")
            elif (audit["acting_identity"], audit["resource"]) != (requester["user_id"], f"claim/{claim_id}"):
                problems.append(f"{case['id']}: the audit row must name the requester and claim/{claim_id}")
    return problems, allowed, denied
# A sentence break: end punctuation, space, capital. "a.m. on" and "(D-002)." don't match.
SENTENCE_BREAK = re.compile(r"[.!?]\s+[A-Z]")


def check_common(case: dict) -> list[str]:
    """Problems any case can have: reasoning, confidence, and YAML that parsed into the wrong shape."""
    problems: list[str] = []
    expected = case["expected"]
    reasoning = expected.get("expected_reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        problems.append("expected_reasoning is missing")
    elif SENTENCE_BREAK.search(reasoning) or not reasoning.rstrip().endswith("."):
        problems.append("expected_reasoning must be exactly one sentence")
    if expected.get("minimum_confidence") not in CONFIDENCE_LEVELS:
        problems.append(f"minimum_confidence must be one of {sorted(CONFIDENCE_LEVELS)}")
    if case.get("split") not in SPLITS:
        problems.append(f"split must be one of {sorted(SPLITS)}")
    # An unquoted comma inside a YAML flow mapping or list splits the value silently.
    for doc in case.get("documents", []):
        if set(doc) - DOCUMENT_KEYS or not isinstance(doc.get("summary"), str):
            problems.append(f"{doc.get('doc_id')}: summary was split by YAML; quote it")
    if not all(isinstance(f, str) for f in expected.get("findings", [])) or len(expected.get("findings", [])) > 1:
        problems.append("findings must be a single quoted statement")
    return problems


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
    staff = data.get("staff", [])
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
        errors += [f"{case['id']}: {p}" for p in check_common(case)]
        if outcome in DECISION_OUTCOMES:
            errors += [f"{case['id']}: {p}" for p in check_case(case, threshold)]
        elif outcome == "REFUSED":
            if case["requester"].get("assigned") is not False:
                errors.append(f"{case['id']}: a refusal case needs an unentitled requester")
            if case["expected"].get("agents_invoked") is not False:
                errors.append(f"{case['id']}: agents must not run on a refused request")
        else:
            errors.append(f"{case['id']}: unknown outcome {outcome}")

    access_problems, allowed, denied = check_access(cases, staff)
    errors += access_problems

    short = {o: counts.get(o, 0) for o in sorted(DECISION_OUTCOMES) if counts.get(o, 0) < MIN_PER_OUTCOME}
    if short:
        errors.append(f"each decision outcome needs at least {MIN_PER_OUTCOME} cases; short: {short}")
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
    print(f"scope matrix: {allowed} requests allowed, {denied} denied (every refusal is a deny, "
          f"every decision case an allow)")
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
