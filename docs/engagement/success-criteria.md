# ClaimSense AI: Success Criteria

Each criterion is written as **metric, threshold, population**, so it can be tested today against the
evaluation set and again at handover. These lines become the acceptance criteria in the week 2
statement of work and the gate in the week 5 evaluation suite.

The **evaluation set** is the versioned case file in `evals/`: 22 cases now (v0: 5 per outcome plus 2 refused-access cases), growing to 150 by
week 5. A **held-out** portion of at least 30 cases is never used for prompt tuning (see D-006).

## The four required criteria

| # | Criterion | Metric | Threshold | Population | How it's measured |
|---|---|---|---|---|---|
| 1 | **Decision accuracy** | Share of claims where the co-pilot's **model-generated** outcome (APPROVE, DENY, FLAG or ROUTE) equals the reference label. A deterministic-fallback verdict, an error or a timeout counts as a miss. | **≥ 85%** overall, and, from week 3, **≥ 80%** on the held-out cases | All decision cases in the evaluation set (20 in v0) | Automated, in CI, on every commit |
| 2 | **Pipeline latency** | Time from request received by the service to recommendation returned. A failed or timed-out call counts at its timeout value. | **p95 ≤ 90 s**, p50 ≤ 45 s | Every decision request on the deployed AWS stack during the full evaluation run. Refused requests are excluded: they never reach an agent and would flatter the percentiles. | CloudWatch metrics on the deployed service |
| 3 | **Adjuster confirmation rate** | Share of recommendations the reviewing adjuster confirms **with the outcome, reasoning and citations all unchanged**. A correct outcome resting on a wrong fact or an unsupported citation is an override. | **≥ 80%** | At least 50 claims reviewed through the confirmation screen | Confirm and override events in the audit log, each override carrying a reason code |
| 4 | **Fraud routing accuracy** | Recall and precision of ROUTE | Recall **≥ 90%**, precision **≥ 70%** | Every case labeled ROUTE (recall) and every case the co-pilot routes (precision) | Automated, in CI |

**Why these numbers:**

1. **85% accuracy.** Adjusters already disagree with each other on the same file, so 100% isn't a
   meaningful target. 85% leaves room for that while staying high enough that confirming is faster
   than redoing. The held-out floor catches a co-pilot tuned to its own test set. Fallback verdicts
   don't count because a verdict the rule table could have produced isn't a model decision.
2. **90 s at p95.** The client asked for minutes instead of hours. 90 s is a defensible ceiling for
   four model calls plus retrieval, and it can be measured from day one of deployment.
3. **80% confirmation.** This is the adoption criterion: it measures whether adjusters trust the
   output enough to use it. Below 80%, adjusters are effectively redoing the work. It differs from
   criterion 1 because it also judges the reasoning and citations: a right answer for the wrong
   reason is not confirmed. In the capstone the reviewer is played by the FDE, who reviews the full
   recommendation against the case file and records a reason code for each override; the report
   says so.
4. **90% recall, 70% precision.** Missing fraud costs more than a false referral, so recall carries
   the higher bar. The precision floor protects SIU from being flooded. The baseline to beat is the
   legacy rule in the client's current rule table (refer when `fraud_score >= 0.5`), measured on the
   same cases; `scripts/check_eval_cases.py` reports it. With 5 ROUTE cases in v0, 90% recall means
   all 5.

## Guardrails (must hold at zero; a breach blocks release)

| Guardrail | Threshold | Population |
|---|---|---|
| Claim data returned to a user not entitled to the claim | **0** | Every access-control case, and every audited request |
| Unsafe approvals: APPROVE where the reference label is DENY or ROUTE | **0** | All decision cases |
| Deterministic fields (term check, payable amount, total-loss ratio) differing from the code-computed value | **0** | All decision cases |
| Coverage statements citing a clause that wasn't in the retrieved set | **0** | All coverage outputs |
| A recommendation recorded as final without adjuster confirmation | **0** | All decision cases, including forced auto-decision cases |
