"""Every synthetic fixture validates against its contract and stays consistent with the eval cases."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pytest
import yaml

import build_fixtures
import check_eval_cases
from claimsense.contracts import Claim, ClaimAssignment, ClauseEntry, Document, Policy

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "synthetic"
CONTRACTS = {"claims": Claim, "assignments": ClaimAssignment, "policies": Policy,
             "documents": Document, "clauses": ClauseEntry}


def load(name: str) -> list[dict]:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cases() -> list[dict]:
    return yaml.safe_load((ROOT / "evals" / "cases_v0.yaml").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("name", CONTRACTS)
def test_every_record_validates(name: str) -> None:
    records = load(name)
    assert records, f"{name}.json is empty"
    for record in records:
        CONTRACTS[name].model_validate(record)


def test_fixtures_are_up_to_date_with_eval_cases(cases: list[dict]) -> None:
    staff = yaml.safe_load((ROOT / "evals" / "cases_v0.yaml").read_text(encoding="utf-8")).get("staff", [])
    built = build_fixtures.build(cases, staff)
    for name, records in built.items():
        on_disk = (DATA / f"{name}.json").read_text(encoding="utf-8")
        assert on_disk == build_fixtures.render(records), f"{name}.json is stale: run scripts/build_fixtures.py"


def test_referential_integrity() -> None:
    claims = {c["claim_id"]: c for c in load("claims")}
    policies = {p["policy_id"] for p in load("policies")}
    assert all(c["policy_id"] in policies for c in claims.values())
    assert {a["claim_id"] for a in load("assignments")} == set(claims)
    assert all(d["meta"]["claim_id"] in claims for d in load("documents"))
    doc_ids = [d["meta"]["doc_id"] for d in load("documents")]
    assert len(doc_ids) == len(set(doc_ids))


def test_every_cited_clause_exists_in_the_corpus(cases: list[dict]) -> None:
    corpus = {c["clause_id"] for c in load("clauses")}
    cited = {cid for case in cases for cid in case["expected"].get("must_cite", [])}
    assert cited <= corpus, f"cited but not in corpus: {sorted(cited - corpus)}"


def test_fixtures_reproduce_the_eval_deterministic_values(cases: list[dict]) -> None:
    """The facts code will read from the fixtures give the same answers the eval cases expect."""
    claims = {c["claim_id"]: c for c in load("claims")}
    policies = {p["policy_id"]: p for p in load("policies")}
    for case in cases:
        det = case["expected"].get("deterministic")
        if not det:
            continue
        claim = claims[case["claim"]["claim_id"]]
        policy = policies[claim["policy_id"]]
        loss = datetime.fromisoformat(claim["loss_datetime"])
        effective = datetime.fromisoformat(policy["effective_date"]).date()
        expiration = datetime.fromisoformat(policy["expiration_date"]).date()
        assert check_eval_cases.in_term(loss, effective, expiration) == det["in_term"], case["id"]
        coverage = check_eval_cases.coverage_for(claim["loss_type"])
        assert (coverage in policy["coverages"]) == det["coverage_present"], case["id"]


def test_assignments_match_requesters(cases: list[dict]) -> None:
    """Entitled requesters own the claim; refused requesters don't (D-003)."""
    owner = {a["claim_id"]: a["adjuster_user_id"] for a in load("assignments")}
    for case in cases:
        user, cid = case["requester"]["user_id"], case["claim"]["claim_id"]
        assert (owner[cid] == user) == case["requester"]["assigned"], case["id"]


SYNTHETIC_TEXT_FIELDS = re.compile(r'"(display_name|named_insured_name|excluded_driver_name|make)": "([^"]*)"')


def test_values_are_obviously_synthetic() -> None:
    text = "".join((DATA / f"{n}.json").read_text(encoding="utf-8") for n in CONTRACTS)
    for field, value in SYNTHETIC_TEXT_FIELDS.findall(text):
        assert value.startswith("Synthetic "), f"{field}={value!r} is not obviously synthetic"
    for vin in re.findall(r'"vin": "([^"]*)"', text):
        assert vin.startswith("SYN") and len(vin) == 17, vin
    assert "@" not in text, "fixtures must not contain email addresses"
