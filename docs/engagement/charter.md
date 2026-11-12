# ClaimSense AI: Engagement Charter

**Client:** a regional motor insurer (personal auto) · **Engagement:** five weeks, discovery to
handover · **FDE:** Adam Mazhar · **Status:** Milestone 1, draft for client sign-off · **Date:** 2026-10-24

## 1. The problem

One adjuster makes every first decision by hand across three systems that don't talk to each other,
taking hours per claim. **(1) The adjuster is the integration layer:** most time goes into assembling
the file, not deciding. **(2) Judgment is invisible:** adjusters disagree on the same file, and the
reasoning lives in inboxes. **(3) Fraud referral is a threshold, not a reading:** a 3 a.m. unwitnessed
loss with a contradictory medical note isn't referred if its score is low. A bigger rule table won't
fix this: coverage turns on clause wording, and fraud on whether the story holds across documents.

## 2. Bottleneck hypothesis

Notice of loss (CMS) → gather the file (document store, CMS) → check coverage (PAS, clause wording) →
assess risk (documents, history) → first decision (CMS). Gathering and coverage dominate handling time,
because that is where the adjuster crosses all three systems. **Validate in week 1:** time 20 recent
claims by step; if wrong, scope moves to where the time goes (logged in DECISIONS.md).

## 3. The three client systems and their integration points

Since Milestone 4, the co-pilot reaches every system only through one governed **MCP door**, under the
adjuster's own token. The door enforces scope in code and audits every call (D-031; matrix in
[access-control.md](access-control.md)).

| System | Owner | What the co-pilot needs | Door tool → integration point |
|---|---|---|---|
| **Claims management (CMS)** | Claims IT, CMS team | Claim, plus the assignment and claim line that scope access | `get_claim` → `GET /claims/{id}`, `/assignment` |
| | | Draft recommendation, reasoning, citations | **The only write:** `submit_draft_recommendation` → `POST /claims/{id}/recommendations`, idempotent |
| **Policy administration (PAS)** | Claims IT, policy systems | Policy as of the loss date: term, payments, coverages, endorsements | `get_policy` → `GET /policies/{id}?as_of=` |
| **Document store** | Claims IT, content services | Police report, estimate, statements, medical notes, photos | `get_claim_documents` → `GET /claims/{id}/documents` |
| **Clause corpus** | Compliance | Policy wording for the claim's form | `search_clauses` (the agents' only tool) |

Also: identity provider (simulated by seat tokens; production is OIDC with token exchange, D-033).

## 4. Target and fixed constraints

Defined in [success-criteria.md](success-criteria.md): reference outcome matched on **≥ 85%** of
evaluation claims; **≤ 90 s at p95**; **≥ 80%** confirmed by the adjuster with outcome, reasoning and
citations unchanged; SIU routing at **≥ 90% recall, ≥ 70% precision**; five zero-tolerance guardrails.
**Fixed:** identity, access, dates and money in code; every judgment cited; an adjuster confirms
every outcome; synthetic data only.

## 5. Decision outcomes and first slice

One outcome per claim, precedence DENY > ROUTE > FLAG > APPROVE (D-002). **APPROVE:** covered, no
specialist handling; code computes the payable. **DENY:** out of term, coverage not bought, or an
exclusion applies. **FLAG:** adjuster must handle first (injury, likely total loss, missing documents).
**ROUTE:** fraud indicators; refer to SIU. An unentitled request is refused before any agent runs.
**First slice:** personal auto physical damage, read-only plus the one write. **Out of scope:**
commercial auto, liability adjudication, payment execution, subrogation.

## 6. Four agent roles (OpenAI Agents SDK)

- **Document Intake:** extracts the facts (vehicle, incident, damage, estimate, injuries, police
  report) from the claim file, each cited to its document.
- **Coverage Check:** reads the retrieved policy clauses against those facts and decides coverage or
  exclusion, citing only retrieved clause IDs; dates and money stay in code.
- **Claim Assessment:** reads the file for fraud indicators and total-loss and injury exposure; the
  legacy fraud score is one input, never the trigger.
- **Decision Draft:** combines coverage, risk and the code-computed facts into one cited draft outcome
  for the adjuster to confirm.

## 7. Top risks (full register: [risk-register.md](risk-register.md))

1. **Fixture and data-access delay** (high): build on our own fixtures; adapters remap later (R1).
2. **OpenAI key limits** (medium): AWS access granted 2026-11-11; token budgets, retry on 429 (R2).
3. **Model misreads coverage** (medium): DENY precedence in code; citation validator (R3).

## 8. Open questions for the client

(1) Handling time by step? (2) Total-loss threshold (assumed 75% of value)? (3) Legacy fraud cutoff (assumed
0.5)? (4) Documents required for theft? (5) Who changes the corpus? (6) Is the status field authoritative (D-004)?
(7) Must a collision have a police report on file before payment (D-025)?
