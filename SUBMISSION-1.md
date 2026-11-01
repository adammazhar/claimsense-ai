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
- [x] Cloud resources created and evidenced: S3 bucket `claimsense-adammazhar-corpus` in my personal AWS account (us-east-1, tagged `project=claimsense`), with all five synthetic fixture files uploaded to `synthetic/`. The IK lab account can't create buckets (section 5).

## 4. Evidence that the stack runs under my own account (one screenshot)

- [x] S3 "Upload succeeded" page for `claimsense-adammazhar-corpus`: 5 files (assignments, claims,
  clauses, documents, policies), 48.9 KB, 0 failures. Included in the Checkpoint 1 PDF, with the IK
  lab account's denial screenshot as blocker evidence (account ID and user name redacted).

## 5. Outstanding blockers

| Blocker | Effect | Since | Ask |
|---|---|---|---|
| **IK lab account (Nuvepro CloudLabs) is restricted** | It denies `s3:CreateBucket` and all Bedrock actions, including listing models (`bedrock:ListFoundationModels`, `bedrock:ListInferenceProfiles`), and has a $10–15 budget with a nightly auto-stop. Cloud evidence comes from my personal AWS account until IK widens the permissions. | 2026-10-31 | Permissions for S3, ECS/ECR, DynamoDB and model access, and a budget that fits a 150-case eval suite |
| **Official synthetic fixtures and solution codebase not shared yet** | IK says they come after the Agentic Research Systems sessions. Claims and clause IDs stay placeholders, built on our own contract-validated fixtures, and are remapped when they land (risk R1). | 2026-10-24 | Delivery date for the fixtures, policy corpus and codebase |
| **OpenAI key is shared across the cohort** | Rate limits and spend are shared; 150-case eval runs may throttle near deadlines (risk R2). | 2026-10-27 | Per-student rate or spend limits, if any |

## Before submitting

- [ ] Re-run `.\.venv\Scripts\python.exe -m pytest` on the commit being submitted, and note the commit hash in the form.
- [ ] Grant the instructors read access to the private repository.
