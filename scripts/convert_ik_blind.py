"""Convert the instructor's synthetic claims CSVs into a blind eval file, evals/blind_ik.yaml.

The CSVs live in docs/ik/w15/review/, which is never committed. The output carries his narratives and
damage descriptions verbatim, so it is git-ignored too. This script holds only the field mapping and
our labels, in our own words, so the file can be rebuilt from his CSVs.

It's a blind set: no prompt or rule is changed because of its results (D-025). Only claims whose facts
clearly justify an outcome are labeled; the rest are left out, not guessed. His claim_status column is
never shown to the models and is not used for labels.

Mapping (D-015 outcome names; his labels approve_first_pass, flag_for_review, route_to_specialist and
deny_coverage_not_in_force are our APPROVE, FLAG, ROUTE and DENY):
- POL-TXA-88000 becomes POL-8000 (last four digits; all 15 stay unique), to fit the PolicyId contract.
- policy_status Expired becomes Lapsed. It is display only either way (D-004).
- Full Coverage gives collision, comprehensive, liability and medical payments; Liability Only gives
  liability alone. Deductibles and the medical payments limit come from his policy row.
- incident_type maps to collision, comprehensive or theft. His dates carry no time, so noon is used.
- His FNOL_FORM becomes the insured's statement, carrying his incident and damage descriptions and the
  injuries_reported and police_report_filed flags. Document types map one to one, except
  RENTAL_RECEIPT, which has no counterpart and doesn't bear on the decision, so it is dropped.
  Documents whose OCR is pending say so, and carry no other text.
- prior_claims_12mo fills prior_claims_24m: a lower bound, since his window is shorter.

Usage:
    python scripts/convert_ik_blind.py   # reads docs/ik/w15/review/*.csv, writes evals/blind_ik.yaml
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "ik" / "w15" / "review"
OUT = ROOT / "evals" / "blind_ik.yaml"

# Our labels, from the facts alone. One line each on why.
LABELS = {
    "CLM-2024-1800": ("APPROVE", "In term with collision coverage, other driver admitted fault, police report, photos and estimate on file, no injury, low score."),
    "CLM-2024-2749": ("APPROVE", "In term with collision coverage, third party at fault with a witness and estimate on file, no injury, low score."),
    "CLM-2024-3041": ("APPROVE", "In term with collision coverage, a minor fender-bender with photos and estimate on file, no injury, low score."),
    "CLM-2024-2530": ("DENY", "The policy expired in January 2023, more than a year before this loss."),
    "CLM-2024-2822": ("DENY", "The loss happened three days after the policy term ended."),
    "CLM-2024-2019": ("DENY", "Hail damage to the insured's own vehicle needs comprehensive coverage, and the policy is liability only."),
    "CLM-2024-2238": ("DENY", "Animal-strike damage to the insured's own vehicle needs comprehensive coverage, and the policy is liability only."),
    "CLM-2024-3114": ("DENY", "Fire damage to the insured's own vehicle needs comprehensive coverage, and the policy is liability only."),
    "CLM-2024-1946": ("FLAG", "In term and covered, but injuries are reported and the estimate exceeds the vehicle's value, so a licensed adjuster handles it."),
    "CLM-2024-2457": ("FLAG", "In term and covered, but injuries are reported and the estimate is 84% of the vehicle's value."),
    "CLM-2024-3187": ("FLAG", "In term and covered, but injuries are reported and the estimate is 92% of the vehicle's value."),
    "CLM-2024-1873": ("ROUTE", "The file contradicts itself: no injuries reported yet a medical report is on file, airbags deployed in an unwitnessed 2 a.m. crash with no police report, and two prior claims."),
}

THEFT = {"Theft recovery", "Carjacking"}
COMPREHENSIVE = {"Hail damage", "Animal strike", "Flood damage", "Vandalism", "Storm damage", "Garage fire"}
DOC_TYPES = {"FNOL_FORM": "insured_statement", "WITNESS_STATEMENT": "witness_statement",
             "POLICE_REPORT": "police_report", "REPAIR_ESTIMATE": "repair_estimate",
             "DAMAGE_PHOTOS": "photos", "MEDICAL_REPORT": "medical_note"}
DOC_TEXT = {"witness_statement": "Written statement from a third-party witness.",
            "police_report": "Police incident report.",
            "photos": "Photographs of the vehicle damage, exterior and interior.",
            "medical_note": "EMS or hospital discharge report."}


def _rows(name: str) -> list[dict]:
    with open(SOURCE / f"claimsense_{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _us_date(text: str) -> date:
    return datetime.strptime(text, "%m/%d/%Y").date()


def _loss_type(incident: str) -> str:
    return "theft" if incident in THEFT else "comprehensive" if incident in COMPREHENSIVE else "collision"


def _coverages(p: dict) -> dict:
    if p["coverage_type"] == "Liability Only":
        return {"liability": {}}
    return {"collision": {"deductible_usd": int(p["collision_deductible_usd"])},
            "comprehensive": {"deductible_usd": int(p["comprehensive_deductible_usd"])},
            "liability": {}, "medical_payments": {"limit_usd": int(p["medpay_limit_usd"])}}


def _documents(claim: dict, docs: list[dict]) -> list[dict]:
    n = claim["claim_id"].split("-")[-1]
    out = []
    for d in docs:
        kind = DOC_TYPES.get(d["document_type"])
        if kind is None:
            continue
        if d["ocr_status"] != "Completed":
            text = "Received. Text not yet extracted (OCR pending)."
        elif kind == "insured_statement":
            text = (f"First notice of loss. {claim['incident_description']} Damage: {claim['damage_description']}. "
                    f"Injuries reported: {claim['injuries_reported'].lower()}. "
                    f"Police report filed: {claim['police_report_filed'].lower()}.")
        elif kind == "repair_estimate":
            text = f"Repair estimate: {claim['damage_description']}, total {int(claim['repair_estimate_usd']):,}."
        else:
            text = DOC_TEXT[kind]
        entry = {"doc_id": f"DOC-{n}-{len(out) + 1}", "type": kind, "summary": text}
        if kind == "photos":
            entry["captured"] = _us_date(d["upload_date"]).isoformat()
        out.append(entry)
    return out


def _deterministic(claim: dict, p: dict, loss: date, loss_type: str, coverages: dict) -> dict:
    estimate, acv = Decimal(claim["repair_estimate_usd"]), Decimal(p["vehicle_acv_usd"])
    in_term = date.fromisoformat(p["policy_start"]) <= loss < date.fromisoformat(p["policy_end"])
    needed = "collision" if loss_type == "collision" else "comprehensive"
    ratio = float((estimate / acv).quantize(Decimal("0.01"), ROUND_HALF_UP))
    facts = {"in_term": in_term, "coverage_present": needed in coverages, "tl_ratio": ratio}
    if in_term and needed in coverages:
        facts["payable_usd"] = int(min(estimate, acv) - coverages[needed]["deductible_usd"])
    return facts


def build() -> dict:
    policies = {r["policy_id"]: r for r in _rows("policies")}
    docs = defaultdict(list)
    for d in _rows("documents"):
        docs[d["claim_id"]].append(d)
    cases = []
    for number, c in enumerate(r for r in _rows("claims") if r["claim_id"] in LABELS):
        outcome, reason = LABELS[c["claim_id"]]
        p = policies[c["policy_id"]]
        loss = _us_date(c["incident_date"])
        loss_type = _loss_type(c["incident_type"])
        coverages = _coverages(p)
        cases.append({
            "id": f"IK-{number + 1:03d}",
            "split": "blind",
            "title": f"{c['incident_type']} ({c['claim_id']})",
            "tags": ["blind", "instructor_data"],
            "requester": {"user_id": "adj-001", "role": "adjuster", "assigned": True},
            "claim": {"claim_id": c["claim_id"], "loss_datetime": f"{loss.isoformat()}T12:00",
                      "loss_type": loss_type, "narrative": c["incident_description"],
                      "repair_estimate_usd": int(c["repair_estimate_usd"]),
                      "fraud_score": float(c["fraud_risk_score"]), "prior_claims_24m": int(c["prior_claims_12mo"])},
            "policy": {"policy_id": f"POL-{c['policy_id'][-4:]}", "effective_date": p["policy_start"],
                       "expiration_date": p["policy_end"],
                       "status_field": "Lapsed" if p["policy_status"] == "Expired" else p["policy_status"],
                       "coverages": coverages, "vehicle_acv_usd": int(p["vehicle_acv_usd"])},
            "documents": _documents(c, docs[c["claim_id"]]),
            "expected": {"outcome": outcome, "expected_reasoning": reason, "minimum_confidence": "medium",
                         "deterministic": _deterministic(c, p, loss, loss_type, coverages)},
        })
    return {"version": 0, "created": date.today().isoformat(), "gate": False,
            "source": "Instructor's synthetic claims CSVs (docs/ik/w15/review). Not committed: verbatim data.",
            "cases": cases}


def main() -> int:
    data = build()
    header = ("# Blind eval set built by scripts/convert_ik_blind.py from the instructor's synthetic CSVs.\n"
              "# Git-ignored: it carries his data verbatim. Report-only: no gate, and nothing is tuned on it.\n")
    OUT.write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120),
                   encoding="utf-8", newline="\n")
    counts = defaultdict(int)
    for case in data["cases"]:
        counts[case["expected"]["outcome"]] += 1
    print(f"wrote {OUT.relative_to(ROOT)}: {len(data['cases'])} cases, {dict(counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
