# ClaimSense AI

A claims adjudication co-pilot for a motor insurer. Given a claim, it returns a first decision
(APPROVE, DENY, FLAG or ROUTE), the reasoning, and the evidence the reasoning rests on. A licensed
adjuster confirms every outcome. Identity, access control, policy dates and money are computed in
code; reading the file and judging it is done by a model, and every judgment is cited.

All data in this repository is synthetic.

## Status

Milestone 1 (discovery and scoping) deliverables drafted for client review; no application code yet.

| Milestone 1 deliverable | File |
|---|---|
| Engagement charter, with the three client systems and their integration points | [docs/engagement/charter.md](docs/engagement/charter.md) |
| Stakeholder map and RACI | [docs/engagement/stakeholders.md](docs/engagement/stakeholders.md) |
| Four quantified success criteria, plus guardrails | [docs/engagement/success-criteria.md](docs/engagement/success-criteria.md) |
| Architectural decision log | [DECISIONS.md](DECISIONS.md) |
| 20 evaluation cases across all four outcomes, including adversarial cases | [evals/cases_v0.yaml](evals/cases_v0.yaml) |

## Known open item: placeholder data

The claims, policies and documents in `evals/cases_v0.yaml`, and every clause ID (`CLS-PER-006`
and the rest), are placeholders written for Milestone 1. They will be replaced or remapped when the
instructor supplies the synthetic fixtures and the policy clause corpus. The scenarios and reference
outcomes are the requirement; the identifiers and field values are not final.

## Checking the evaluation cases

Requires Python 3.12 or later.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\check_eval_cases.py
```

The script recomputes every deterministic value in the cases (policy term, payable amount,
total-loss ratio, days since inception, photo dates against inception) and fails if a label
disagrees or a deterministic field has no check. It also reports how the client's current fraud
rule (refer when the legacy score is 0.5 or more) performs on the same cases: on v0 it refers two
claims, one of them wrongly, and catches only one of the four that should go to SIU (recall 25%,
precision 50%).
