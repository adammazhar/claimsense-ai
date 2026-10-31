# Submission 1: Checkpoint

**Due:** Saturday Oct 31, 2026, before the Week 3 class on Sunday Nov 1. Submitted through the
course Google Form. Not graded; required regardless of completeness.

## 1. Capstone repository URL

- [x] https://github.com/adammazhar/claimsense-ai (private; grant the instructors access before submitting)

## 2. Milestone 1 deliverables

- [x] Engagement charter, 2 pages: problem, three client systems and integration points, success criteria, four agent roles, top risks: `docs/engagement/charter.md`
- [x] Stakeholder map with each stakeholder typed user, blocker or enabler; RACI by Week 1–5 deliverable and by decision (approver, reviewer, daily user, who can block rollout): `docs/engagement/stakeholders.md`
- [x] Four quantified success criteria, plus guardrails: `docs/engagement/success-criteria.md`
- [x] DECISIONS.md with dated decisions and reasons (D-001 to D-007 for M1, D-008 to D-016 since)
- [x] 22 evaluation cases: 5 per outcome plus 2 refused-access cases, including adversarial cases: `evals/cases_v0.yaml`

## 3. Milestone 2 deliverables

- [x] Statement of work, 2 pages: `docs/engagement/sow.md`
- [x] Architecture diagram, every flow labeled, code/model boundary explicit: `docs/architecture/architecture.md`
- [x] Pricing model with assumptions stated: `docs/engagement/pricing.md`, reproduced by `scripts/pricing.py`
- [x] Risk register, 8 risks with likelihood, impact, mitigation, owner, early-warning signal: `docs/engagement/risk-register.md`
- [x] Typed contracts for all three client systems, with the idempotency rule for the write: `src/claimsense/contracts/`, `docs/architecture/contracts.md`
- [x] Synthetic data shapes for claims, policies and documents: `data/schemas/`, `data/synthetic/`
- [ ] **Cloud account provisioned, with created resources evidenced: blocked, see section 5**

## 4. Evidence that the stack runs under my own account (one screenshot)

- [ ] Screenshot of the running service or the provisioned AWS resources. **Not possible yet**: the
  IK AWS account isn't provisioned. Fallback if it hasn't arrived by Oct 31: a screenshot of the
  passing `pytest` run, plus a GitHub Actions run if CI is set up by then, labeled as local
  evidence.

## 5. Outstanding blockers

| Blocker | Effect | Since | Ask |
|---|---|---|---|
| **IK AWS account not provisioned** | Can't create or evidence resources (Milestone 2, item 7), and no cloud screenshot for this submission. Week 3 container work proceeds locally. | 2026-10-27 | Account and budget or quota limits, before Nov 1 |
| **Official synthetic fixtures and policy corpus not yet supplied** | Claims and clause IDs are placeholders. Retrieval and coverage citations will need remapping when they land (risk R1). | 2026-10-24 | Delivery date for the fixtures and corpus |
| **OpenAI key is shared across the cohort** | Rate limits and spend are shared; 150-case eval runs may throttle near deadlines (risk R2). | 2026-10-27 | Per-student rate or spend limits, if any |

## Before submitting

- [ ] Re-run `.\.venv\Scripts\python.exe -m pytest` on the commit being submitted, and note the commit hash in the form.
- [ ] Update this file if the AWS account arrives before Oct 31.
