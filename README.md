# ClaimSense AI

A claims adjudication co-pilot for a motor insurer. Given a claim, it returns a first decision
(APPROVE, DENY, FLAG or ROUTE), the reasoning, and the evidence the reasoning rests on. A licensed
adjuster confirms every outcome. Identity, access control, policy dates and money are computed in
code; reading the file and judging it is done by a model, and every judgment is cited.

All data in this repository is synthetic.

## Status

Milestones 1 and 2 drafted for client review. Milestone 3 (the working agent pipeline under change
control) is built; see below. Submission 1 checklist: [SUBMISSION-1.md](SUBMISSION-1.md).

| Milestone 1: discovery and scoping | File |
|---|---|
| Engagement charter, with the three client systems and their integration points | [docs/engagement/charter.md](docs/engagement/charter.md) |
| Stakeholder map and RACI | [docs/engagement/stakeholders.md](docs/engagement/stakeholders.md) |
| Four quantified success criteria, plus guardrails | [docs/engagement/success-criteria.md](docs/engagement/success-criteria.md) |
| Architectural decision log | [DECISIONS.md](DECISIONS.md) |
| 22 evaluation cases: 5 per outcome plus 2 refused-access cases, including adversarial cases | [evals/cases_v0.yaml](evals/cases_v0.yaml) |

| Milestone 2: SoW, pricing and architecture | File |
|---|---|
| Statement of work (2 pages) | [docs/engagement/sow.md](docs/engagement/sow.md) |
| Architecture diagram, code/model boundary, alternatives | [docs/architecture/architecture.md](docs/architecture/architecture.md) |
| Pricing model with assumptions, reproduced by a script | [docs/engagement/pricing.md](docs/engagement/pricing.md), [scripts/pricing.py](scripts/pricing.py) |
| Risk register | [docs/engagement/risk-register.md](docs/engagement/risk-register.md) |
| Typed contracts for the three client systems, with the idempotency rule | [docs/architecture/contracts.md](docs/architecture/contracts.md), [src/claimsense/contracts/](src/claimsense/contracts/) |
| Synthetic data shapes: JSON Schemas and fixtures | [data/schemas/](data/schemas/), [data/synthetic/](data/synthetic/) |
| Cloud account | **Not provisioned yet: pending from IK** (see below) |

## Run it

```powershell
docker compose up --build
```

That starts the co-pilot and the three mock client systems, with healthchecks, on the mock brain: no key
and no cost. Only the co-pilot is published, on port 8000. Then:

```powershell
curl.exe -X POST http://localhost:8000/v1/claims/CLM-2026-0001/recommendation -H "X-User-Id: adj-001" -H "Content-Type: application/json" -d "{}"
```

Each response says who decided: `verdict_source` is `model` or `deterministic_fallback`, `deterministic`
holds what code computed, and `judgment` holds what the model concluded. To use the real models, put
`OPENAI_API_KEY` in `.env` and run `$env:BRAIN="openai"; docker compose up --build`.

**Do not expose this service yet.** Identity is an unverified header until Milestone 4 (D-023).

## Milestone 3: where it stands

| Measure | Mock brain | Live models (one run, 2026-11-04) | Target |
|---|---|---|---|
| Decision accuracy (model verdicts only) | 100% of 20 | **70% of 20** | 85% |
| Held-out accuracy | 100% of 6 | **66.7% of 6** | 80% |
| Fraud routing recall / precision | 100% / 100% | **60% / 100%** | 90% / 70% |
| Adversarial and access-control cases | 7/7, 2/2 | 7/7, 2/2 | all |
| Guardrail breaches | 0 | 0 | 0 |

**The CI gate is green, and the live models don't yet meet the acceptance criteria.** The gate runs on
the mock brain, which proves the pipeline, guardrails and gate work; it doesn't measure model judgment
(D-018). See [docs/evidence/m3/](docs/evidence/m3/README.md).

## Cloud account: pending

IK provides the AWS account for the capstone, and it has not been provisioned yet. Until it is, the
AWS components in the architecture are marked "planned, pending IK account", and nothing in the
build depends on them (D-012, risk R2). The OpenAI key is the existing IK key, kept out of the
repository. When the account arrives, the created resources will be evidenced here and in
SUBMISSION-1.md.

## Known open item: placeholder data

The claims, policies and documents in `evals/cases_v0.yaml`, and every clause ID (`CLS-PER-006`
and the rest), are placeholders written for Milestone 1. The same is true of the fixtures and clause
wording in `data/synthetic/`, which are generated from those cases. They will be replaced or remapped
when the instructor supplies the synthetic fixtures and the policy clause corpus. The scenarios and
reference outcomes are the requirement; the identifiers and field values are not final.

## Checks

Requires Python 3.12 or later.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest                         # contracts, fixtures, idempotency, pricing, eval checker
.\.venv\Scripts\python.exe scripts\check_eval_cases.py       # eval-case consistency on its own
.\.venv\Scripts\python.exe scripts\pricing.py                # reproduce every number in pricing.md
.\.venv\Scripts\python.exe scripts\build_fixtures.py         # regenerate data/synthetic/ from the eval cases
.\.venv\Scripts\python.exe scripts\generate_schemas.py       # regenerate data/schemas/ from the contracts
.\.venv\Scripts\python.exe scripts\run_evals.py              # the eval gate on the mock brain; exit 1 if it fails
.\.venv\Scripts\python.exe scripts\run_evals.py --brain openai  # the same suite on the live models; costs about $0.40
```

`check_eval_cases.py` recomputes every deterministic value in the cases (policy term, payable
amount, total-loss ratio, days since inception, photo dates against inception). It fails if a label
disagrees or a deterministic field has no check. It also reports how the client's current fraud
rule (refer when the legacy score is 0.5 or more) performs on the same cases: on v0 it refers two
claims, one of them wrongly, and catches only one of the five that should go to SIU (recall 20%,
precision 50%).
