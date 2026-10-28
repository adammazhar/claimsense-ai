"""docs/engagement/pricing.md and sow.md quote the numbers scripts/pricing.py produces, and the method holds."""

from __future__ import annotations

from pathlib import Path

import pricing

DOCS = Path(__file__).resolve().parent.parent / "docs" / "engagement"
DOC = (DOCS / "pricing.md").read_text(encoding="utf-8")
SOW = (DOCS / "sow.md").read_text(encoding="utf-8")


def test_headline_numbers_in_doc_match_script() -> None:
    r = pricing.results()
    m, p = pricing.money, pricing.pct
    figures = [
        m(r["rate"]), m(r["cost_rate"]), f"${r['hourly']:,.2f}", f"${r['cost_hourly']:,.2f}",
        p(r["labor_margin"]), p(r["labor_margin_avg_utilization"]), p(r["labor_margin_big_tech_pay"]),
        m(r["expenses"]), m(r["tokens"]), m(r["access_buffer"]), m(r["pessimistic_high_cost"]),
        *(m(v) for v in r["tm_price"].values()), *(m(v) for v in r["cost"].values()),
        m(r["margin_floor"]), m(r["margin_expected"]), p(r["floor_gross_margin"]),
        m(r["revenue_per_engineer"]), m(r["floor_per_engineer"]),
        m(-r["high_case_floor_gap"]), m(r["high_access_billable"]), m(r["high_after_9a"]),
        m(r["high_after_9a_with_bonus"]), m(r["high_access_on_time"]),
        *(m(amount) for _, amount in r["payments"]),
        m(r["models"][1]["margin_if_overrun"]),
    ]
    for role, cph in r["role_costs"]:
        figures += [f"${cph:,.2f}", p(1 - cph / role.bill_rate), f"${role.pay_anchor:,}"]
    for model in r["models"]:
        figures += [m(model["expected"]), m(model["min"]), m(model["max"]), m(model["margin"]),
                    p(model["gross_margin"])]
    missing = [f for f in figures if f not in DOC]
    assert not missing, f"pricing.md is out of date with scripts/pricing.py: {missing}"


def test_rate_card_is_in_the_doc_and_drives_the_blended_rate() -> None:
    for role in pricing.ROLES:
        assert role.name in DOC and f"**${role.bill_rate}/h**" in DOC and f"{role.share:.0%}" in DOC, role.name
    assert pricing.blended_rate() == pricing.blended_hourly() * pricing.HOURS_PER_DAY


def test_price_is_rate_card_times_days_and_cost_is_separate() -> None:
    est = pricing.estimate()
    assert pricing.tm_price(est["exp"]) == est["exp"] * pricing.blended_rate() + pricing.expenses()
    assert pricing.cost(est["exp"]) < pricing.tm_price(est["exp"])


def test_labor_and_floor_gross_margin_are_in_the_consulting_range() -> None:
    lo, hi = pricing.GROSS_MARGIN_BAND
    r = pricing.results()
    assert lo <= r["labor_margin"] <= hi
    assert lo <= r["floor_gross_margin"] <= hi


def test_recommended_floor_clears_expected_cost_and_buffer() -> None:
    r = pricing.results()
    assert r["margin_floor"] > 0
    lo, hi = pricing.REVENUE_PER_ENGINEER_BAND
    assert lo <= r["revenue_per_engineer"] <= hi


def test_sow_quotes_the_script_prices_and_rate_card() -> None:
    r = pricing.results()
    for figure in (r["recommended"]["floor"], *(amount for _, amount in r["payments"])):
        assert pricing.money(figure) in SOW, f"sow.md doesn't quote {pricing.money(figure)}"
    for role in pricing.ROLES:
        assert f"${role.bill_rate}/h" in SOW, f"sow.md change-order rate card is missing {role.name}"
    assert "(b) Delivery overrun" in SOW


def test_buffer_applies_only_to_the_high_end() -> None:
    est = pricing.estimate()
    assert est["low"] == sum(pricing.TSHIRT[m.size][0] for m in pricing.MILESTONES)
    assert est["high"] > sum(pricing.TSHIRT[m.size][1] for m in pricing.MILESTONES)


def test_bonus_is_capped_and_zero_without_a_production_pilot() -> None:
    rec = pricing.results()["recommended"]
    assert rec["min"] == rec["floor"]
    assert rec["max"] == rec["floor"] + pricing.BONUS_CAP_CONFIRMATIONS * pricing.BONUS_PER_CONFIRMATION
