"""Build the synthetic fixtures in data/synthetic/ from the evaluation cases.

The eval cases are the single source of truth (D-014): every claim, policy and document here is
derived from evals/cases_v0.yaml, and every record is validated against the Pydantic contracts
before it is written. Values the cases don't carry (VINs, party names, timestamps) are generated
deterministically and are obviously synthetic: VINs start "SYN", people are "Synthetic ... NNN".

Clause wording is written here, once, for the clause IDs the cases cite. It is placeholder text
until the instructor supplies the policy corpus.

Usage:
    python scripts/build_fixtures.py          # write data/synthetic/*.json
    python scripts/build_fixtures.py --check  # fail if the files on disk are out of date
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from claimsense.contracts import (  # noqa: E402
    Claim,
    ClaimAssignment,
    ClauseEntry,
    Document,
    DocumentMeta,
    Endorsement,
    Policy,
)

CASES = ROOT / "evals" / "cases_v0.yaml"
OUT = ROOT / "data" / "synthetic"
FORM = "SYN-PA-01"
FORM_EDITION = date(2026, 1, 1)
DESK = "PD-AUTO-1"

# Placeholder clause wording, synthetic, for the clause IDs cited in the eval cases.
CLAUSES = [
    ("CLS-PER-006", "General provisions", "Policy period and territory",
     "This policy applies only to accidents and losses which occur during the policy period. The policy "
     "period begins at 12:01 a.m. local time on the effective date and ends at 12:01 a.m. local time on "
     "the expiration date shown in the Declarations.", ["policy_period"]),
    ("CLS-DEC-001", "Declarations", "Coverage applies only where a premium is shown",
     "Coverage is provided only for those coverages for which a premium is shown in the Declarations "
     "for the insured vehicle.", ["declarations"]),
    ("CLS-COL-001", "Part D: Damage to your auto", "Collision insuring agreement",
     "We will pay for direct and accidental loss to your covered auto caused by collision with another "
     "object or by upset, minus the applicable deductible shown in the Declarations.", ["collision"]),
    ("CLS-CMP-001", "Part D: Damage to your auto", "Other than collision insuring agreement",
     "We will pay for direct and accidental loss to your covered auto not caused by collision, including "
     "glass breakage, hail, fire and theft, minus the applicable deductible.", ["comprehensive", "theft"]),
    ("CLS-EXC-003", "Part D: Exclusions", "Public or livery conveyance",
     "We do not provide coverage for loss to your covered auto while it is being used to carry persons or "
     "property for a fee, including use through a ride-hailing application.", ["exclusion", "livery"]),
    ("CLS-DRV-002", "Endorsements", "Named driver exclusion",
     "No coverage is provided for any claim arising from an accident or loss that occurs while your "
     "covered auto is being operated by a driver named as excluded in this endorsement.", ["endorsement", "excluded_driver"]),
    ("CLS-BI-001", "Part A: Liability", "Bodily injury liability",
     "We will pay damages for bodily injury for which an insured becomes legally responsible because of "
     "an auto accident. Bodily injury claims are handled by a licensed adjuster.", ["liability", "injury"]),
    ("CLS-MED-001", "Part B: Medical payments", "Medical payments coverage",
     "We will pay reasonable expenses for necessary medical services because of bodily injury sustained "
     "by an insured in an auto accident, up to the limit shown in the Declarations.", ["medical_payments", "injury"]),
    ("CLS-TL-001", "Part D: Limit of liability", "Total loss settlement",
     "Our limit of liability is the lesser of the actual cash value of the damaged property or the amount "
     "necessary to repair it. A vehicle may be declared a total loss when repair cost approaches its "
     "actual cash value.", ["total_loss"]),
    ("CLS-DUT-001", "Part E: Duties after an accident or loss", "Duties after loss",
     "A person seeking coverage must promptly notify us of the loss and, in the event of theft, promptly "
     "notify the police. We may require these duties to be met before payment.", ["duties", "theft"]),
    ("CLS-FRD-001", "General provisions", "Concealment or fraud",
     "We do not provide coverage for any insured who has made fraudulent statements or engaged in "
     "fraudulent conduct in connection with any accident or loss for which coverage is sought.", ["fraud"]),
]

# Claims that appear in an eval case without a policy (refusal cases) get a minimal one.
REFUSAL_POLICIES = {
    "CLM-2026-0019": {"policy_id": "POL-1019", "effective_date": "2026-03-01", "expiration_date": "2026-09-01",
                      "status_field": "Active", "coverages": {"collision": {"deductible_usd": 500}},
                      "vehicle_acv_usd": 15000},
}
REFUSAL_ASSIGNEES = {"CLM-2026-0019": "adj-003"}
CAPTURED_RE = re.compile(r"captured (\d{4}-\d{2}-\d{2})")


def _num(n: int) -> int:
    return int(n.split("-")[-1]) if isinstance(n, str) else n


def _utc(d: date, hh: int) -> str:
    return datetime.combine(d, time(hh, 0)).isoformat() + "Z"


def _coverages(raw: dict) -> dict:
    out = {}
    for name, terms in (raw or {}).items():
        terms = terms or {}
        out[name] = {k: v for k, v in {"deductible": terms.get("deductible_usd"), "limit": terms.get("limit_usd")}.items()
                     if v is not None}
    return out


def build(cases: list[dict]) -> dict[str, list[dict]]:
    """Return the fixture files as {name: [records]}, each record validated against its contract."""
    claims, policies, assignments, documents = {}, {}, {}, []
    for case in cases:
        c = case["claim"]
        cid = c["claim_id"]
        if "loss_datetime" not in c:  # EV-020 reuses EV-001's claim
            continue
        n = _num(cid)
        loss = c["loss_datetime"] if isinstance(c["loss_datetime"], datetime) else datetime.fromisoformat(c["loss_datetime"])
        reported = loss.date() + timedelta(days=1)
        p = case.get("policy") or REFUSAL_POLICIES[cid]
        vin = "SYNTEST0019CANARY" if cid == "CLM-2026-0019" else f"SYNTESTVIN{n:07d}"
        party = {"party_id": f"PTY-{n:04d}", "display_name": f"Synthetic Insured {n:04d}"}

        claims[cid] = Claim.model_validate({
            "claim_id": cid, "policy_id": p["policy_id"], "loss_datetime": loss, "loss_type": c["loss_type"],
            "narrative": c["narrative"],
            "vehicle": {"vin": vin, "year": 2018 + n % 7, "make": "Synthetic Motors", "model": "Test Sedan"},
            "claimant": party, "repair_estimate": c.get("repair_estimate_usd", 0),
            "legacy_fraud_score": c["fraud_score"], "prior_claims_24m": c["prior_claims_24m"],
            "reported_at": _utc(reported, 9),
        }).model_dump(mode="json")

        effective = date.fromisoformat(str(p["effective_date"]))
        transactions = [{"on": effective.isoformat(), "type": "issued"}]
        transactions += [{"on": str(e["date"]), "type": e["event"], **({"note": e["note"]} if e.get("note") else {})}
                         for e in p.get("payment_history", [])]
        endorsements = [Endorsement.model_validate({"type": e["type"], "form_number": "SYN-END-DRV-02",
                                                    "excluded_driver_name": e["name"]}).model_dump(mode="json")
                        for e in p.get("endorsements", [])]
        policies[p["policy_id"]] = Policy.model_validate({
            "policy_id": p["policy_id"], "as_of": loss.date(), "form_number": FORM,
            "named_insured": party["party_id"], "named_insured_name": party["display_name"],
            "effective_date": effective, "expiration_date": str(p["expiration_date"]),
            "status_field": p["status_field"], "transactions": transactions,
            "coverages": _coverages(p.get("coverages")), "endorsements": endorsements,
            "vehicle_acv": p["vehicle_acv_usd"],
        }).model_dump(mode="json")

        assignee = case["requester"]["user_id"] if case["requester"].get("assigned") else REFUSAL_ASSIGNEES[cid]
        assignments[cid] = ClaimAssignment.model_validate({
            "claim_id": cid, "adjuster_user_id": assignee, "desk": DESK, "assigned_at": _utc(reported, 10),
        }).model_dump(mode="json")

        for d in case.get("documents", []):
            text = d["summary"]
            captured = d.get("captured") or (m.group(1) if (m := CAPTURED_RE.search(text)) else None)
            meta = DocumentMeta.model_validate({
                "doc_id": d["doc_id"], "claim_id": cid, "type": d["type"], "received_at": _utc(reported, 11),
                "captured_on": str(captured) if captured else None,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            })
            documents.append(Document(meta=meta, text=text).model_dump(mode="json"))

    clauses = [ClauseEntry(clause_id=cid, form_number=FORM, form_edition=FORM_EDITION, section=section,
                           heading=heading, text=text, tags=tags).model_dump(mode="json")
               for cid, section, heading, text, tags in CLAUSES]
    return {
        "claims": list(claims.values()),
        "assignments": list(assignments.values()),
        "policies": list(policies.values()),
        "documents": documents,
        "clauses": clauses,
    }


def render(records: list[dict]) -> str:
    return json.dumps(records, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]
    files = build(cases)
    stale = []
    for name, records in files.items():
        path = OUT / f"{name}.json"
        text = render(records)
        if "--check" in argv:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(path.name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path.relative_to(ROOT)} ({len(records)} records)")
    if stale:
        print(f"out of date, run scripts/build_fixtures.py: {', '.join(stale)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
