"""Estimate and price the ClaimSense pilot. Reproduces every number in docs/engagement/pricing.md.

Method from the Week 14 notebook (T-shirt sizing with per-class risk buffers, three pricing models
plus fixed floor and outcome bonus, margin check), applied to this engagement's own milestones.

Price and cost are separate (D-011):
- PRICE: what the client pays. Billable days x the US rate card by role (8-hour day), plus expenses
  at cost. That is the T&M price; the fixed floor is built from it.
- COST: what delivery costs us. Each role's internal loaded cost per billable hour, from a stated
  pay anchor, a benefits loading and a billable-utilization assumption, all cited in pricing.md.

Stdlib only. Usage:
    python scripts/pricing.py
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------- method (from the notebook)
TSHIRT = {"S": (3, 5), "M": (8, 12), "L": (15, 25), "XL": (30, 50)}  # days, low-high
RISK_BUFFER = {  # multiplier on the HIGH end, per risk class
    "low": 1.10,              # work we've done before: documents, contracts
    "integration": 1.35,      # three client systems, auth, audit
    "access_politics": 1.80,  # waiting on the AWS account, fixtures, corpus, controls review
    "novel": 1.50,            # agent judgment quality and a 150-case eval suite are unproven
}
PESSIMISTIC_ACCESS = 2.20  # notebook's sensitivity run


@dataclass(frozen=True)
class Milestone:
    name: str
    size: str
    risk_class: str


MILESTONES = [
    Milestone("M1 Discovery and scoping", "S", "low"),
    Milestone("M2 SoW, architecture, contracts, data shapes", "M", "low"),
    Milestone("Access gate: AWS account, fixtures, corpus, controls review", "M", "access_politics"),
    Milestone("M3 Four agents, retrieval with citations, CI eval gate", "L", "novel"),
    Milestone("M4 Data-access service, auth on every route, audit, two-user test", "L", "integration"),
    Milestone("M5 150-case evals, dashboard and alarm, drill, runbook, handover", "L", "novel"),
]


@dataclass(frozen=True)
class Role:
    name: str
    bill_rate: int  # USD per hour the client pays (the rate card)
    share: float  # share of engagement days
    pay_anchor: int  # annual total compensation we pay (Levels.fyi anchor, see pricing.md)
    anchor_source: str


# ---------------------------------------------------------------- assumptions (all stated in pricing.md)
ROLES = [
    Role("Principal FDE / architect", 325, 0.30, 220_000, "Levels.fyi FDE median"),
    Role("Senior AI engineer", 275, 0.40, 171_000, "Levels.fyi FDE 25th percentile"),
    Role("Engagement manager", 250, 0.10, 185_000, "Levels.fyi TPM 25th percentile"),
    Role("Evaluation / QA engineer", 200, 0.20, 135_000, "Levels.fyi data scientist 25th percentile"),
]
# Sensitivity: what the same roles cost at big-tech market pay instead of boutique pay.
BIG_TECH_PAY = {"Principal FDE / architect": 290_000, "Senior AI engineer": 250_000,
                "Engagement manager": 244_500, "Evaluation / QA engineer": 180_000}
HOURS_PER_DAY = 8
WORKING_DAYS = 25  # five weeks, Nov 21 end date fixed
WAGE_SHARE_OF_COMP = 0.70  # BLS ECEC, June 2026: wages are 70.0% of private-industry compensation
HOURS_PER_YEAR = 2080
UTILIZATION = 0.75  # SPI 2026 benchmark: 75% target, reached by high performers
UTILIZATION_AVERAGE = 0.664  # SPI 2026 benchmark: 2025 average, a record low

# Expenses, passed through at cost: tooling and PM, AWS run cost, model tokens.
TOOLING_AND_PM = 6000
AWS_RUN_COST = 1500
TOKENS_IN_PER_RUN, TOKENS_OUT_PER_RUN = 24_000, 3_000  # four agent calls on one claim
PRICE_IN_PER_M, PRICE_OUT_PER_M = 2.50, 10.00  # USD per million tokens; placeholder, re-check price sheet
EVAL_CASES, EVAL_RUNS_PER_DAY, BUILD_DAYS, DEV_MULTIPLIER = 150, 2, 15, 2.0

# Access-politics buffer: what waiting costs us, separate from the access milestone's work.
ACCESS_DELAY_WEEKS = 1.0  # IK AWS account and official fixtures both pending at Oct 27
IDLE_FRACTION = 0.5  # share of the team blocked while waiting; the rest builds on our own fixtures

# Outcome: a recommendation the adjuster CONFIRMS unchanged (criterion 3), counted from the CMS
# audit log's AdjusterDecisionEvent records, never from the co-pilot's own count.
BONUS_PER_CONFIRMATION = 15.00
DESK_CLAIMS_PER_MONTH = 1200  # personal auto physical-damage desk volume (assumption to confirm)
BONUS_WINDOW_WEEKS = 8  # supervised production pilot after handover, once controls review passes
CONFIRMATION_RATE = {"low": 0.0, "expected": 0.80, "high": 0.95}  # low = production pilot never approved
BONUS_CAP_CONFIRMATIONS = 2000
ADJUSTER_HOURS_SAVED, ADJUSTER_LOADED_RATE = 2.5, 55.00  # value per claim, to show the bonus is a fair share

# Pricing-model parameters, all relative to the expected T&M price.
TM_CAP_MULTIPLE = 1.25  # T&M ceiling = 1.25 x expected T&M price
FIXED_RISK_PREMIUM = 0.20  # fixed price = expected T&M x 1.20: the vendor carries the overrun
OUTCOME_FLOOR_SHARE = 0.80  # pure outcome model: floor at 80% of expected T&M, rest earned by bonus
FLOOR_SHARE = 1.00  # recommended: floor = expected T&M price; bonus is the only upside
FIXED_OVERRUN = 1.25
PAYMENT_SCHEDULE = [("M2 sign-off, Oct 31", 0.30), ("M4 sign-off, Nov 14", 0.40), ("M5 acceptance, Nov 21", 0.30)]
REVENUE_PER_ENGINEER_BAND = (600_000, 1_000_000)
GROSS_MARGIN_BAND = (0.35, 0.45)


# ---------------------------------------------------------------- arithmetic
def _check_mix() -> None:
    assert abs(sum(r.share for r in ROLES) - 1.0) < 1e-9


def loaded_cost_per_hour(pay: float, utilization: float = UTILIZATION) -> float:
    """Annual pay, loaded for benefits, spread over the billable hours a year actually has."""
    return pay / WAGE_SHARE_OF_COMP / (HOURS_PER_YEAR * utilization)


def blended_hourly() -> float:
    """Blended bill rate: what the client pays per hour across the staffing mix."""
    _check_mix()
    return sum(r.bill_rate * r.share for r in ROLES)


def blended_rate() -> float:
    """Blended bill rate per day."""
    return blended_hourly() * HOURS_PER_DAY


def blended_cost_hourly(pay: dict[str, float] | None = None, utilization: float = UTILIZATION) -> float:
    """Blended internal cost per billable hour."""
    _check_mix()
    return sum(loaded_cost_per_hour((pay or {}).get(r.name, r.pay_anchor), utilization) * r.share for r in ROLES)


def blended_cost_rate(**kw) -> float:
    return blended_cost_hourly(**kw) * HOURS_PER_DAY


def gross_margin_on_labor(**kw) -> float:
    return 1 - blended_cost_hourly(**kw) / blended_hourly()


def estimate(buffers: dict[str, float] = RISK_BUFFER) -> dict:
    rows, low, exp, high = [], 0.0, 0.0, 0.0
    for m in MILESTONES:
        lo, hi = TSHIRT[m.size]
        e, hb = (lo + hi) / 2, hi * buffers[m.risk_class]
        rows.append({"name": m.name, "size": m.size, "risk": m.risk_class, "range": f"{lo}-{hi}",
                     "buffer": buffers[m.risk_class], "low": lo, "exp": e, "high": hb})
        low, exp, high = low + lo, exp + e, high + hb
    return {"rows": rows, "low": low, "exp": exp, "high": high}


def model_tokens_cost() -> float:
    per_run = TOKENS_IN_PER_RUN / 1e6 * PRICE_IN_PER_M + TOKENS_OUT_PER_RUN / 1e6 * PRICE_OUT_PER_M
    return per_run * EVAL_CASES * EVAL_RUNS_PER_DAY * BUILD_DAYS * DEV_MULTIPLIER


def expenses() -> float:
    return TOOLING_AND_PM + AWS_RUN_COST + model_tokens_cost()


def tm_price(days: float) -> float:
    """What the client pays on T&M: days at the rate card plus expenses at cost."""
    return days * blended_rate() + expenses()


def cost(days: float) -> float:
    """What delivery costs us: days at our loaded cost plus the same expenses."""
    return days * blended_cost_rate() + expenses()


def team_fte(days: float) -> float:
    return days / WORKING_DAYS


def access_buffer(exp_days: float) -> float:
    return ACCESS_DELAY_WEEKS * 5 * team_fte(exp_days) * IDLE_FRACTION * blended_cost_rate()


def confirmations(scenario: str) -> float:
    claims = DESK_CLAIMS_PER_MONTH * 12 / 52 * BONUS_WINDOW_WEEKS
    return claims * CONFIRMATION_RATE[scenario]


def bonus(scenario: str, capped: bool = True) -> float:
    n = confirmations(scenario)
    return (min(n, BONUS_CAP_CONFIRMATIONS) if capped else n) * BONUS_PER_CONFIRMATION


def price_models(est: dict) -> list[dict]:
    c = cost(est["exp"])
    tm = tm_price(est["exp"])
    cap = tm * TM_CAP_MULTIPLE
    fixed = tm * (1 + FIXED_RISK_PREMIUM)
    outcome_floor = tm * OUTCOME_FLOOR_SHARE
    floor = tm * FLOOR_SHARE
    models = [
        {"model": "T&M with a cap", "expected": tm, "min": tm_price(est["low"]),
         "max": min(tm_price(est["high"]), cap)},
        {"model": "Fixed-price", "expected": fixed, "min": fixed, "max": fixed,
         "margin_if_overrun": fixed - c * FIXED_OVERRUN},
        {"model": "Outcome-based", "floor": outcome_floor, "expected": outcome_floor + bonus("expected", capped=False),
         "min": outcome_floor + bonus("low", capped=False), "max": outcome_floor + bonus("high", capped=False)},
        {"model": "Fixed floor + outcome bonus", "floor": floor, "expected": floor + bonus("expected"),
         "min": floor + bonus("low"), "max": floor + BONUS_CAP_CONFIRMATIONS * BONUS_PER_CONFIRMATION},
    ]
    for m in models:
        m["margin"] = m["expected"] - c
        m["gross_margin"] = m["margin"] / m["expected"]
    return models


def results() -> dict:
    est = estimate()
    c = {k: cost(est[d]) for k, d in (("low", "low"), ("expected", "exp"), ("high", "high"))}
    buf = access_buffer(est["exp"])
    models = price_models(est)
    rec = models[-1]
    years = WORKING_DAYS / 5 / 52
    pess_high = estimate(dict(RISK_BUFFER, access_politics=PESSIMISTIC_ACCESS))["high"]
    # The high case. Clause 9a bills the access line's overrun above expected at the rate card;
    # whatever remains is delivery overrun on a fixed floor, which clause 9b re-plans.
    access = next(row for row in est["rows"] if row["risk"] == "access_politics")
    access_billable = (access["high"] - access["exp"]) * blended_rate()
    high_gap = rec["floor"] - c["high"]
    return {
        "estimate": est, "rate": blended_rate(), "hourly": blended_hourly(),
        "cost_rate": blended_cost_rate(), "cost_hourly": blended_cost_hourly(),
        "labor_margin": gross_margin_on_labor(),
        "labor_margin_avg_utilization": gross_margin_on_labor(utilization=UTILIZATION_AVERAGE),
        "labor_margin_big_tech_pay": gross_margin_on_labor(pay=BIG_TECH_PAY),
        "role_costs": [(r, loaded_cost_per_hour(r.pay_anchor)) for r in ROLES],
        "expenses": expenses(), "tokens": model_tokens_cost(),
        "tm_price": {k: tm_price(est[d]) for k, d in (("low", "low"), ("expected", "exp"), ("high", "high"))},
        "cost": c, "fte": team_fte(est["exp"]), "access_buffer": buf,
        "pessimistic_high_cost": cost(pess_high),
        "models": models, "recommended": rec,
        "confirmations": {s: confirmations(s) for s in CONFIRMATION_RATE},
        "margin_floor": rec["floor"] - c["expected"] - buf,
        "margin_expected": rec["expected"] - c["expected"] - buf,
        "floor_gross_margin": (rec["floor"] - c["expected"]) / rec["floor"],
        "high_case_floor_gap": high_gap,
        "high_access_billable": access_billable,
        "high_after_9a": high_gap + access_billable,
        "high_after_9a_with_bonus": high_gap + access_billable + bonus("expected"),
        # Every other line at its high end, access on time: 9a recovers nothing.
        "high_access_on_time": rec["floor"] - (c["high"] - (access["high"] - access["exp"]) * blended_cost_rate()),
        "revenue_per_engineer": rec["expected"] / (team_fte(est["exp"]) * years),
        "floor_per_engineer": rec["floor"] / (team_fte(est["exp"]) * years),
        "value_per_claim": ADJUSTER_HOURS_SAVED * ADJUSTER_LOADED_RATE,
        "payments": [(label, share * rec["floor"]) for label, share in PAYMENT_SCHEDULE],
    }


def money(v: float) -> str:
    return f"-${-v:,.0f}" if v < 0 else f"${v:,.0f}"


def pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def main() -> None:
    r = results()
    est = r["estimate"]
    print("ESTIMATE (days; high end carries the per-class buffer)")
    for row in est["rows"]:
        print(f"  {row['name']:66.66} {row['size']:2} {row['range']:>5} x{row['buffer']:.2f}"
              f"  {row['low']:4.0f} {row['exp']:5.1f} {row['high']:6.1f}")
    print(f"  {'TOTAL':66} {'':2} {'':>5} {'':5}  {est['low']:4.0f} {est['exp']:5.1f} {est['high']:6.1f}")
    print(f"Team {r['fte']:.1f} FTE over {WORKING_DAYS} working days\n")
    print("RATE CARD (bill) vs LOADED COST (ours), per hour")
    for role, cph in r["role_costs"]:
        print(f"  {role.name:28} bill ${role.bill_rate}  cost ${cph:,.2f}  margin {pct(1 - cph / role.bill_rate)}"
              f"  ({role.share:.0%} of days; pay ${role.pay_anchor:,}, {role.anchor_source})")
    print(f"  Blended: bill ${r['hourly']:,.2f}/h = {money(r['rate'])}/day; cost ${r['cost_hourly']:,.2f}/h = "
          f"{money(r['cost_rate'])}/day; labor gross margin {pct(r['labor_margin'])}")
    print(f"  Sensitivity: at {UTILIZATION_AVERAGE:.1%} utilization {pct(r['labor_margin_avg_utilization'])}; "
          f"at big-tech pay {pct(r['labor_margin_big_tech_pay'])}")
    print(f"Expenses at cost {money(r['expenses'])} (model tokens {money(r['tokens'])})")
    print("T&M price low / expected / high: " + " / ".join(money(r["tm_price"][k]) for k in ("low", "expected", "high")))
    print("Cost low / expected / high: " + " / ".join(money(r["cost"][k]) for k in ("low", "expected", "high")))
    print(f"Access-politics buffer {money(r['access_buffer'])}; "
          f"high cost at {PESSIMISTIC_ACCESS}x access buffer {money(r['pessimistic_high_cost'])}\n")
    print("PRICING (expected / min / max / expected margin / gross margin)")
    for m in r["models"]:
        print(f"  {m['model']:28} {money(m['expected']):>10} {money(m['min']):>10} {money(m['max']):>10}"
              f" {money(m['margin']):>10} {pct(m['gross_margin']):>7}")
    print(f"  Fixed-price margin after a 25% cost overrun: {money(r['models'][1]['margin_if_overrun'])}")
    rec = r["recommended"]
    print(f"\nRECOMMENDED: floor {money(rec['floor'])}, expected {money(rec['expected'])}, max {money(rec['max'])}")
    c = r["confirmations"]
    print(f"Confirmations in the bonus window: low {c['low']:.0f}, expected {c['expected']:.0f}, high {c['high']:.0f}"
          f" (cap {BONUS_CAP_CONFIRMATIONS}); value per claim {money(r['value_per_claim'])}")
    print(f"Margin check: floor - cost - buffer = {money(r['margin_floor'])}; with expected bonus = "
          f"{money(r['margin_expected'])}; floor gross margin {pct(r['floor_gross_margin'])}")
    print(f"High case: floor - high cost = {money(r['high_case_floor_gap'])}; 9a bills the access overrun "
          f"{money(r['high_access_billable'])} -> {money(r['high_after_9a'])}, "
          f"{money(r['high_after_9a_with_bonus'])} with the expected bonus; access on time, other lines high: "
          f"{money(r['high_access_on_time'])}")
    lo, hi = REVENUE_PER_ENGINEER_BAND
    print(f"Revenue per engineer (annualized): expected {money(r['revenue_per_engineer'])}, floor only "
          f"{money(r['floor_per_engineer'])} (band {money(lo)}-{money(hi)})")
    print("Payments: " + "; ".join(f"{label} {money(v)}" for label, v in r["payments"]))


if __name__ == "__main__":
    main()
