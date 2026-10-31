# ClaimSense AI: Statement of Work

**Vendor:** Adam Mazhar, FDE · **Client:** a regional motor insurer (personal auto) · **Engagement:**
claims adjudication co-pilot, pilot · **Version:** v0.1, 2026-10-27

**1. Background and objectives.** One adjuster makes every first decision by hand across claims
management (CMS), policy administration (PAS) and the document store. It takes hours per claim, the
reasoning isn't recorded, and fraud referral fires on a score threshold. Objective: a first pass in
minutes, reasoning recorded, a licensed adjuster accountable for every outcome (`charter.md`).

## 2. Scope, deliverables and timeline (weeks run Sunday to Saturday)

| Milestone (week) | Deliverables | Sign-off |
|---|---|---|
| **M1** Discovery (Oct 18–24) | Charter, RACI, 4 success criteria, DECISIONS.md, 22 eval cases | Sat Oct 24, VP Claims |
| **M2** SoW and design (Oct 25–31) | SoW, architecture, pricing, risk register, typed contracts, synthetic data shapes, cloud account | Sat Oct 31, VP Claims, CISO |
| **M3** Agents (Nov 1–7) | 4 typed agents, retrieval citing retrieved clauses, one-command container stack, CI eval gate blocking image push | Sat Nov 7, Quality Lead |
| **M4** Access (Nov 8–14) | Data-access service, auth on every route, access check before any agent, two-user test, audit on every call | Sat Nov 14, CISO |
| **M5** Handover (Nov 15–21) | 150-case adversarial suite, dashboard and alarm, incident drill, runbook, demo, handover pack | Sat Nov 21, VP Claims, Compliance |

## 3. Acceptance criteria (copied from success-criteria.md)

1. **Decision accuracy.** Accepted when the model-generated outcome matches the reference label on
   ≥ 85% of decision cases and ≥ 80% of held-out cases; fallbacks, errors and timeouts count as misses.
2. **Pipeline latency.** Accepted when p95 ≤ 90 s and p50 ≤ 45 s on the deployed stack over the full
   evaluation run, refusals excluded.
3. **Adjuster confirmation.** Accepted when ≥ 80% of ≥ 50 reviewed recommendations are confirmed with
   outcome, reasoning and citations unchanged, per the audit log.
4. **Fraud routing.** Accepted when ROUTE recall ≥ 90% and precision ≥ 70%.
5. **Guardrails.** Accepted when each of the five guardrails is 0: unentitled data returned, unsafe
   approvals, deterministic mismatches, unretrieved citations, outcomes made final unconfirmed.

**4. Out of scope.** Commercial auto, liability adjudication, payment execution, subrogation, changes
to the legacy fraud score, any write besides the draft, production or personal data, and the
production pilot and its controls review (a separate SoW).

**5. Pricing and payment.** Fixed floor **$191,430**, the expected effort at the rate card plus
expenses at cost: $57,429 at M2, $76,572 at M4, $57,429 at M5 acceptance. Bonus of **$15 per
confirmed recommendation**, capped at 2,000, during an 8-week production pilot, counted from the CMS
audit log and reconciled by the Quality Lead, never the co-pilot's own count (`pricing.md`).

**6. IP and licensing.** On final payment the client owns the **agents** (definitions,
orchestration, contracts), the **prompts** and their versions, and the **embeddings and derived
data** (clause index, eval results), which are deleted from vendor systems at exit. **Fine-tunes:**
none are made in the pilot; any later fine-tune on client data is the client's and is never reused.
The vendor keeps its pre-existing tooling, licensed to the client royalty-free for this system.

## 7. Data annex

| Data | Where it lives | Retention | Deletion | Subprocessors |
|---|---|---|---|---|
| Synthetic claims, policies, documents, corpus | Repo; S3 (planned) | Engagement + 30 days | Bucket emptied, repo handed over | AWS |
| Prompts and agent I/O | OpenAI API in transit; CloudWatch | Logs 30 days | Log groups deleted | OpenAI, AWS |
| Audit log | DynamoDB (planned) | Engagement + 90 days, exported | Table deleted after export | AWS |

**Synthetic data only, at every stage**: no production or personally identifiable data enters any
system or subprocessor. The OpenAI key lives in Secrets Manager and is never committed.

**8. Security and compliance.** Entitlement is checked in code before any agent runs; agents have no
tools that reach client systems; every call is audited; the co-pilot only creates drafts.

**9. Change control.** Changes are requested in writing and estimated within 2 working days; no work
starts before a signed change order. Change orders bill at the rate card: principal $325/h, senior
AI engineer $275/h, engagement manager $250/h, evaluation engineer $200/h, 8-hour day. **(a) Access delay:** if
the AWS account or the official fixtures miss **Sun Nov 1**, dates move day for day or extra days
are billed, capped. **(b) Delivery overrun:** if M3 or M4 misses sign-off, M5 is re-planned by
change order (scope or dates) before work continues.

**10. Assumptions and dependencies.** IK provides the AWS account (pending) and the shared OpenAI
key; until official fixtures arrive we build on our own. The Quality Lead gives 2 hours a week.

**11. Exit and offboarding.** The client receives the repository, runbook, eval suite, audit export
and handover pack; vendor data is deleted within 30 days, in writing, and vendor access revoked.

**12. Signatures.** Vendor: ____________________ · Client (VP of Claims): ____________________
