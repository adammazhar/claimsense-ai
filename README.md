# ClaimSense AI

A claims adjudication co-pilot for a motor insurer. Given a claim, it returns a first decision
(APPROVE, DENY, FLAG or ROUTE), the reasoning, and the evidence the reasoning rests on. A licensed
adjuster confirms every outcome. Identity, access control, policy dates and money are computed in
code; reading the file and judging it is done by a model, and every judgment is cited.

All data in this repository is synthetic.

## Status

Milestones 1 and 2 drafted for client review. Contracts, fixtures and checks are code; the agents
themselves are Milestone 3. Submission 1 checklist: [SUBMISSION-1.md](SUBMISSION-1.md).

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
```

`check_eval_cases.py` recomputes every deterministic value in the cases (policy term, payable
amount, total-loss ratio, days since inception, photo dates against inception). It fails if a label
disagrees or a deterministic field has no check. It also reports how the client's current fraud
rule (refer when the legacy score is 0.5 or more) performs on the same cases: on v0 it refers two
claims, one of them wrongly, and catches only one of the five that should go to SIU (recall 20%,
precision 50%).
