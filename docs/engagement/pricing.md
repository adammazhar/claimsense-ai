# ClaimSense AI: Pricing Model

Worked top to bottom: the cost first, then the price, and the price has to clear the cost. Every
number here is produced by [`scripts/pricing.py`](../../scripts/pricing.py) (`python
scripts/pricing.py`), which follows the Week 14 notebook's method: T-shirt sizing, per-class risk
buffers, the three pricing models plus fixed floor and outcome bonus, and the margin check.
`tests/test_pricing.py` fails if a number below drifts from the script. Amounts are USD.

**Framing.** This prices the engagement as a real one with a US motor insurer, staffed by a delivery
team. The capstone is delivered by one FDE on the brief's calendar, so the effort figures are
notional; the method, the assumptions and the risk logic are the deliverable.

**Price and cost are separate** (D-011):

- **Price** is what the client pays: billable days × the US rate card by role, on an 8-hour day,
  plus expenses at cost. That is the T&M price, and the fixed floor is built from it.
- **Cost** is what delivery costs us: each role's internal loaded cost per billable hour, set in
  section 2.

## 1. Rate card: the bill rate the client pays

| Role | Bill rate | Share of days | Primary anchor: GSA CALC federal ceiling rate for the category (n records) |
|---|---|---|---|
| Principal FDE / architect | **$325/h** | 30% | Artificial intelligence (181): median $193.59, p75 $259.31, **p90 $304.12**, max $485.47 |
| Senior AI engineer | **$275/h** | 40% | Machine learning (110): median $174.02, **p75 $227.01**, p90 $266.24, max $445.99 |
| Engagement manager | **$250/h** | 10% | Program manager (10,281): median $183.22, **p75 $222.19**, p90 $265.47 |
| Evaluation / QA engineer | **$200/h** | 20% | Data scientist (1,516): median $169.28, **p75 $205.01**, p90 $244.59; quality assurance (4,212): median $112.54, p90 $183.44 |
| **Blended** | **$272.50/h = $2,180/day** | 100% | |

**How the rate card sits against CALC.** The rates sit at roughly the 75th to 90th percentile of the
federal ceiling rates for their categories, with the principal just above the AI category's p90.

- **Why that's market, not high.** CALC ceilings are the most a federal agency may pay under a GSA
  schedule, and schedule prices are negotiated against the vendor's commercial pricing, so they sit
  at or below what commercial clients pay. They are also rates for all experience levels: senior
  specialists sit in the upper percentiles.
- **The evaluation engineer.** Priced against data science (p75 $205), not generic quality
  assurance, because the work is building and scoring a 150-case adversarial evaluation suite.

**What the client pays.** At expected effort the T&M price is $191,430, so the client pays the rate
card, and the margin comes out of the gap between the rate card and our cost (section 2), not from a
markup on top of it.

### Primary sources

- **GSA CALC (Contract-Awarded Labor Category), ceiling rates API v3**,
  `api.gsa.gov/acquisition/calc/v3/api/ceilingrates/?keyword=…`, queried Oct 27–28, 2026 (data
  timestamp 2026-10-28). The keywords were "artificial intelligence", "machine learning", "program
  manager", "data scientist" and "quality assurance".
  - **What the figures are.** Percentiles and counts come from the API's own aggregations over all
    matching records, not a sample.
  - **The experience filter didn't work.** It was not applied by the API (results were identical
    with and without it), so seniority is read from the percentiles.
- **Levels.fyi**, US total compensation (base, stock and bonus), pages updated Oct 23–28, 2026:
  - [Forward deployed engineer](https://www.levels.fyi/t/software-engineer/title/forward-deployed-engineer):
    median $220,000; p25 $171K, p75 $290K, p90 $351K.
  - [ML/AI software engineer](https://www.levels.fyi/t/software-engineer/focus/ml-ai): median $250,000.
  - [Technical program manager](https://www.levels.fyi/t/technical-program-manager): median $244,500
    (1,492 salaries); p25 $185K, p75 $310K, p90 $391K.
  - [Data scientist](https://www.levels.fyi/t/data-scientist): median $180,000 (3,310 salaries);
    p25 $135K, p75 $252K, p90 $340K.
  - [Palantir FDE](https://www.levels.fyi/companies/palantir/salaries/software-engineer/title/forward-deployed-engineer):
    median $232,500.
- **BLS, Employer Costs for Employee Compensation**,
  [June 2026, released Sep 9, 2026](https://www.bls.gov/news.release/ecec.nr0.htm): private
  industry wages are $32.82 of $46.89 per hour worked, i.e. **70.0%** of compensation, and benefits
  are 30.0%.
- **SPI Research, 2026 Professional Services Maturity Benchmark** (509 firms), via
  [Deltek's summary](https://www.deltek.com/resources/articles/professional-services-billable-utilization-historic-low/):
  billable utilization averaged **66.4%** in 2025, a record low, against a **75%** target that
  high-performing firms reach.

### Supporting references (vendor guides; not used to set any number)

These are secondary sources from vendors and consultancies. They agree that the rate card is
mid-market for senior AI specialists.

- [lazige.agency](https://lazige.agency/guides/ai-consultant-pricing-us), updated Oct 24, 2026:
  boutique AI specialist $250–$450/h.
- [FactoryJet](https://factoryjet.com/blog/ai-consultant-cost-2026), compiling 2026 guides: senior or
  specialized $300–$500+/h; Big Four day rates $2,500–$3,500+.
- [Fortune](https://fortune.com/2025/09/14/ai-engineers-consultant-premium-enterprise-data-integration-high-pay-llms-big-four),
  Sep 14, 2025: one enterprise AI company bills consultant-FDEs at $900/h; Big Four partners around
  $400–$600/h. This is one company's price, noted as upside.
- [KORE1](https://www.kore1.com/it-consulting-rates/), 2026-Q4: generic contract-staffing rates
  (senior data engineer $118–$140/h), which these specialist roles price above.

## 2. Cost: our internal loaded cost per role

**The formula.** Loaded cost per billable hour = annual pay ÷ 0.70 (benefits loading, BLS) ÷
(2,080 hours × 75% billable utilization, SPI target). That is 1,560 billable hours a year.

| Role | Pay anchor (annual total comp) | Loaded cost/h | Bill rate | Gross margin |
|---|---|---|---|---|
| Principal FDE / architect | $220,000, Levels.fyi FDE median | $201.47 | $325 | 38.0% |
| Senior AI engineer | $171,000, Levels.fyi FDE 25th percentile | $156.59 | $275 | 43.1% |
| Engagement manager | $185,000, Levels.fyi TPM 25th percentile | $169.41 | $250 | 32.2% |
| Evaluation / QA engineer | $135,000, Levels.fyi data scientist 25th percentile | $123.63 | $200 | 38.2% |
| **Blended** | | **$164.74/h = $1,318/day** | **$272.50/h** | **39.5%** |

**How the anchors were chosen.** Levels.fyi is dominated by big-tech and frontier-lab submissions,
which pay a large part of compensation in stock. A boutique consultancy pays nearer the lower half of
that distribution, so each role is anchored at the percentile a boutique would pay. The principal is
at the FDE median and the others are at the 25th percentile. Applying the benefits loading to total
compensation, stock included, is conservative: it overstates cost slightly.

**Sensitivity.** The margin depends on two things, and both are stated:

- **Utilization.** At SPI's 2025 *average* of 66.4%, rather than the 75% target, the labor gross
  margin falls to **31.7%**, below the 35–45% range. Utilization is the lever a delivery lead
  controls.
- **Pay.** At **big-tech pay** (FDE p75 for the principal, then the ML/AI, TPM and data scientist
  medians), the same rate card leaves **16.8%**. A firm paying frontier-lab compensation needs
  frontier rates, which is why the Fortune figure exists. At these rates, we staff at boutique pay.

## 3. Estimate: effort, price and cost

| Milestone | Size | Day range | Risk class (×) | Days low / exp / high |
|---|---|---|---|---|
| M1 Discovery and scoping | S | 3–5 | low (1.10) | 3 / 4 / 5.5 |
| M2 SoW, architecture, contracts, data shapes | M | 8–12 | low (1.10) | 8 / 10 / 13.2 |
| Access gate: AWS account, fixtures, corpus, controls review | M | 8–12 | access politics (1.80) | 8 / 10 / 21.6 |
| M3 Four agents, retrieval with citations, CI eval gate | L | 15–25 | novel (1.50) | 15 / 20 / 37.5 |
| M4 Data-access service, auth on every route, audit, two-user test | L | 15–25 | integration (1.35) | 15 / 20 / 33.8 |
| M5 150-case evals, dashboard and alarm, drill, runbook, handover | L | 15–25 | novel (1.50) | 15 / 20 / 37.5 |
| **Total** | | | | **64 / 84 / 149.1** |

As in the notebook, the buffer multiplies only the high end, and it is set per risk class, not as a
flat 20%. The access gate is its own line because it's work in its own right: chasing the AWS account,
mapping the official fixtures and corpus onto our contracts, and answering the controls review.
84 expected days over 25 working days is a **3.4 FTE** team.

- **Expenses at cost: $8,310**, passed through on every model. Tooling and project management
  $6,000; AWS run cost $1,500; model tokens $810. The token figure is 150 cases × 2 eval runs a day ×
  15 build days × 2 for development runs, at 24,000 input and 3,000 output tokens per claim, priced at
  $2.50 and $10 per million tokens. Those per-token prices are placeholders: re-check the OpenAI price
  sheet before signing, and re-measure the tokens per claim in week 3.
- **T&M price (low / expected / high): $147,830 / $191,430 / $333,239**: days × $2,180 + expenses.
- **Cost (low / expected / high): $92,659 / $119,018 / $204,750**: days × $1,318 + expenses.

**What moves the number.** The access line moves it most: at the notebook's pessimistic 2.2× access
buffer, the high cost rises to $211,076. The two novel lines are next.

## 4. Access-politics buffer

**$11,071** = 1 week of delay × 5 days × 3.4 FTE × 50% of the team blocked × $1,318 (our cost per day).

- **Why 1 week.** At Oct 27 the IK AWS account is not provisioned, and the official fixtures and
  policy corpus arrive later with the solution codebase.
- **Why 50%.** We don't stop when blocked: we build on our own fixtures (D-014) and a local stack, so
  only part of the team is idle.

This buffer is the cost of waiting, which is separate from the access-gate milestone's work, and it
is held back from margin in the check in section 8.

## 5. The three pricing models

| Model | You bill on | Risk sits with | When to pick it |
|---|---|---|---|
| T&M with a cap | days at the rate card, ceiling-bounded | shared | scope still fuzzy |
| Fixed-price | the milestone set | vendor | discovery was strong |
| Outcome-based | confirmed recommendations | shared, results-linked | the outcome is clean and someone other than the vendor counts it |

**The outcome.** The outcome is a recommendation the licensed adjuster **confirms with the outcome,
reasoning and citations unchanged**: success criterion 3, exactly. A draft, an override, or anything
the co-pilot reports about itself doesn't count.

**Who counts.** The count comes from the client's **CMS audit log**: `AdjusterDecisionEvent` records
with `action = confirmed` (see [contracts.md](../architecture/contracts.md)). The CMS writes these
when the adjuster acts, not the co-pilot. The **Claims Quality Lead** reconciles the count monthly
against a 5% sample, and the invoice uses the reconciled number. **The agent's own count is never used.**

## 6. Price the pilot, four ways (expected cost $119,018)

| Model | Expected | Min | Max | Expected margin | Gross margin | How it's built |
|---|---|---|---|---|---|---|
| T&M with a cap | $191,430 | $147,830 | $239,288 | $72,412 | 37.8% | days × rate card + expenses; cap 1.25 × expected |
| Fixed-price | $229,716 | $229,716 | $229,716 | $110,698 | 48.2% | expected T&M × 1.20 risk premium; margin after a 25% cost overrun is $80,944 |
| Outcome-based | $179,729 | $153,144 | $184,713 | $60,711 | 33.8% | floor at 80% of expected T&M, plus $15 per confirmation, uncapped |
| **Fixed floor + outcome bonus** | **$218,015** | **$191,430** | **$221,430** | **$98,997** | **45.4%** | floor = expected T&M; plus $15 per confirmation, capped at 2,000 |

**The bonus basis.**
- **The window.** The bonus is paid on confirmations during an **8-week supervised production pilot
  after handover**, on the personal auto physical-damage desk.
- **The volume.** At an assumed 1,200 claims a month, that is 2,215 claims. At the 80% confirmation
  target that's 1,772 confirmations, or 2,105 at 95%; the bonus is capped at 2,000. The low case is 0,
  because the production pilot needs the controls review to approve production data. This SoW
  doesn't cover that review: the SoW is synthetic-only.
- **Why $15 is fair.** The value per claim is about $138 (2.5 adjuster hours saved × $55 loaded), so
  $15 is about 11% of the value and the client keeps the rest.

## 7. Recommendation

**Chosen model: fixed floor + outcome bonus. Floor $191,430, capped bonus up to $30,000, maximum $221,430.**

- **Procurement gets a ceiling.** It's known on day one, and it equals the expected T&M price at the
  rate card: the client pays the market rate for the expected effort, no more.
- **We carry the overrun.** The floor is fixed, so overrun risk sits with us (section 8), which is
  what the client is buying instead of T&M.
- **The VP of Claims gets alignment.** The bonus pays only when adjusters confirm the output.
- **Why not the others.** Pure fixed price, at $229,716, is safer for us, but the 20% premium is hard
  to defend while access delays are the client's. Pure outcome-based is rejected: with synthetic data
  only, no confirmation can happen before handover.
- **Payment.** 30% of the floor on M2 sign-off (Oct 31, $57,429), 40% on M4 sign-off (Nov 14,
  $76,572), and 30% on M5 acceptance (Nov 21, $57,429). The bonus is invoiced at the end of the bonus
  window.

## 8. Margin check

| Check | Result |
|---|---|
| Floor gross margin | **37.8%**, inside the 35–45% range |
| Floor − expected cost − access buffer | **$61,342** |
| Expected revenue − expected cost − access buffer | **$87,926** |
| Revenue per engineer, annualized (÷ 3.4 FTE ÷ 5 weeks) | **$674,807** expected, inside the $0.6–1.0M band; **$592,521** on the floor alone, just below it |
| High-case cost against the floor | **−$13,320** before change control |

**The high case, honestly.** If the access gate and both novel lines all run to their buffered highs,
cost reaches $204,750 and the floor alone falls **$13,320** short. The SoW's change control
(section 9) covers it:

- **9a, access delay.** If the AWS account, or the official fixtures and corpus, aren't available by
  **Sun Nov 1**, the dates move day for day, or the extra days are billed at the rate card. Billing
  the access line's overrun above expected (11.6 days × $2,180 = **$25,288**) turns the high case into
  **+$11,968**, or +$38,552 with the expected bonus.
- **9b, delivery overrun.** If M3 or M4 misses its sign-off, M5 is re-planned by change order (scope
  or dates, at the rate card) before work continues. In the high case this is a second line of
  defense, not a requirement: after 9a the floor already covers the high cost.

**The case 9a doesn't cover.** If access is on time but every other line runs to its buffered high,
9a recovers nothing, and the floor clears that cost by only **$1,968**: effectively break-even. 9b is
the lever before it gets there: M5 is re-planned at the M3 or M4 sign-off that slips, not
discovered at the end.

## Assumptions to confirm with the client

1. Desk volume of 1,200 personal auto physical-damage claims a month.
2. 2.5 adjuster hours saved per claim, at a $55 loaded hourly cost.
3. Production pilot starts within 30 days of handover, or the bonus lapses.
4. OpenAI token prices and tokens per claim, re-measured in week 3. First measurement (2026-11-04, D-017): about 12,000 input and 800 output tokens per claim, about $0.019 per claim, against the 24,000 and 3,000 assumed here. The inputs in `scripts/pricing.py` stay as they are, which is conservative.
5. AWS run cost of $1,500 for five weeks, re-measured once the IK account exists (D-012).
6. The rate card and the cost anchors in sections 1 and 2, re-checked against CALC and Levels.fyi
   before signing.
