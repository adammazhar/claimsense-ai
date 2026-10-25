# ClaimSense AI: Engagement Charter

**Client:** a regional motor insurer (personal auto) · **Engagement:** five weeks, discovery to
handover · **FDE:** Adam Mazhar · **Status:** Milestone 1, draft for client sign-off · **Date:** 2026-10-24

## 1. The problem

One adjuster makes every first decision by hand across three systems that don't talk to each other:
open the claim, find the policy, pull documents, re-key values, check coverage, judge fraud, total
loss and injury, write the decision. Hours per claim, and the queue waits on one pair of hands. **(1) The adjuster is the integration
layer:** most handling time goes into assembling the file, not deciding. **(2) Judgment is
invisible:** adjusters disagree on the same file, and the reasoning lives in inboxes. **(3) Fraud
referral is a threshold, not a reading:** a 3 a.m. unwitnessed loss with a contradictory medical note
isn't referred if its legacy score is low. Extending the rule table won't fix this: coverage turns on
clause wording, and fraud on whether the story holds across documents. Rules read fields; this job
requires reading the whole file.

## 2. Bottleneck hypothesis

A claim moves through five steps: **(1)** notice of loss (CMS) → **(2)** gather the file (document
store, CMS) → **(3)** check coverage (PAS, then the clause wording) → **(4)** assess risk (documents,
claim history) → **(5)** first decision (CMS). Hypothesis: steps 2 and 3 dominate handling time,
because that is where the adjuster crosses all three systems. **To validate in week 1:** time 20
recent claims by step with the client; if steps 2 and 3 aren't most of it, scope moves to where the
time goes, recorded in DECISIONS.md.

## 3. The three client systems and their integration points

| System | What the co-pilot needs from it | Integration point |
|---|---|---|
| **Claims management (CMS)** | Claim: loss time, narrative, vehicle, claimant, legacy fraud score, prior claims | Read `GET /claims/{id}` |
| | Assignment: the source of truth for entitlement | Read `GET /claims/{id}/assignment` |
| | Draft recommendation, reasoning, citations | **Write (the only one)** `POST /claims/{id}/recommendations`, idempotent on claim + `run_id` |
| **Policy administration (PAS)** | Policy as of the loss date: term, payment and cancellation history, coverages, limits, deductibles, endorsements | Read `GET /policies/{id}?as_of={loss_date}` |
| **Document store** | Police report, estimate, statements, medical notes, photo metadata | Read `GET /claims/{id}/documents`, `GET /documents/{id}` |

Outside the three systems sit the **identity provider** and the **policy clause corpus** (form
wordings, searchable by clause ID). All access goes through one engagement-owned service that checks
token and entitlement before any agent runs and audits every call, granted or refused.

## 4. Target and fixed constraints

Defined in [success-criteria.md](success-criteria.md): reference outcome matched on **≥ 85%** of
evaluation claims; recommendation in **≤ 90 s at p95**; **≥ 80%** confirmed by the reviewing adjuster
with outcome, reasoning and citations unchanged; Special Investigations Unit (SIU) routing at **≥ 90%
recall, ≥ 70% precision**; five zero-tolerance guardrails. **Fixed:** identity, access control, policy
dates and money stay in code; every model judgment cites its evidence; a licensed adjuster confirms
every outcome; synthetic data only, no production or personally identifiable data.

## 5. Decision outcomes and first slice

One outcome per claim; precedence DENY > ROUTE > FLAG > APPROVE (D-002). **APPROVE:** policy responds,
no risk needs specialist handling; code computes the payable amount. **DENY:** policy doesn't respond
(out of term, coverage not bought, exclusion applies). **FLAG:** likely covered, but an adjuster must
handle it first (injury, likely total loss, missing documents). **ROUTE:** fraud indicators; refer to
SIU. An unentitled request is not an outcome: it is refused before any agent runs, with no claim data.
**First slice:** personal auto physical damage (collision, comprehensive), all four outcomes, read-only
access plus the one write above; injury and total loss are flagged, not adjudicated. **Out of scope:**
commercial auto, liability adjudication, payment execution, subrogation, the legacy fraud score itself.

## 6. Open questions for the client

(1) Handling time per claim, by step? Settles the bottleneck hypothesis. (2) Total-loss threshold?
Assumed 75% of actual cash value, as in the current rule table. (3) Legacy fraud cutoff? Assumed a
score of 0.5, as in the current rule table; it is the baseline to beat. (4) Documents required before
paying a theft or hit-and-run claim? (5) Who may change the clause corpus, and how are form revisions
versioned? (6) Is the policy status field ever authoritative over term dates? Assumed not (D-004).
