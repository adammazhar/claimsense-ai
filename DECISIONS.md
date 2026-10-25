# DECISIONS.md

Engagement decision log for ClaimSense AI. One entry per real decision, newest last. Each entry
records what was decided, why, what was rejected, who owns it, and what would reopen it.

---

## D-001 · 2026-10-24 · Deterministic spine, model judgment only where reading is required

- **Decision:** Identity, entitlement, policy-term checks, coverage presence, deductibles, limits,
  total-loss ratio and payable amounts are computed in Python. The model is used only for work that
  requires reading: interpreting clause wording against the facts, judging narrative consistency
  across documents, and drafting the reasoning.
- **Why:** These are the operations where a wrong answer is a legal or financial error, and code is
  exact and testable. The client's own example, a claim paid on a lapsed policy because the status
  field was stale, is a date comparison, not a judgment.
- **Alternatives considered:** (a) Extend the client's rule table. Rejected: rules read fields, and
  coverage and fraud depend on wording and on consistency across documents. (b) Let the model do the
  whole adjudication, including dates and amounts. Rejected: not exactly reproducible, and it violates
  a fixed constraint of the brief.
- **Owner:** FDE (Adam Mazhar)
- **Revisit when:** A judgment step turns out to be fully expressible as a rule. Then it moves into
  code.

## D-002 · 2026-10-24 · Four outcomes with a fixed precedence; refusal is not an outcome

- **Decision:** The co-pilot returns exactly one of APPROVE, DENY, FLAG or ROUTE. When several apply,
  precedence is **DENY > ROUTE > FLAG > APPROVE**: if the policy doesn't respond, the claim is denied
  whatever else is true. An unentitled request is refused before any agent runs and returns no
  outcome and no claim data.
- **Why:** A fixed precedence makes the reference labels unambiguous, which decision accuracy depends
  on. Keeping refusal outside the outcome set makes it structurally impossible for a model to
  "decide" to show data to the wrong person.
- **Alternatives considered:** (a) Multiple simultaneous outcomes (for example, "flag and route").
  Rejected: harder to label and to measure, and an adjuster needs one next action. (b) ROUTE above
  DENY. Rejected: a claim on a policy that doesn't respond is denied regardless; SIU can still be
  told through a separate note.
- **Owner:** FDE, to be confirmed with the Claims Quality Lead
- **Revisit when:** The client's SIU wants fraud referrals even on out-of-term claims.

## D-003 · 2026-10-24 · Access control is code that runs before any agent

- **Decision:** Every request carries a token. The data-access service resolves the user, checks
  entitlement against the CMS assignment record, and only then fetches claim data and invokes the
  agents. Denied requests return no claim data. Every request, granted or denied, writes an audit
  record with user, action and resource.
- **Why:** If unentitled data never reaches the model, no prompt injection can leak it. This is the
  trust boundary the brief grades (area D, 20 points).
- **Alternatives considered:** (a) Tell the model in its instructions not to reveal other users'
  claims. Rejected: a prompt isn't a control, and the brief rates it Weak. (b) Filter the model's
  output after the fact. Rejected: the data would already have reached the model.
- **Owner:** FDE
- **Revisit when:** The client requires agents to act on behalf of the user against their systems
  (on-behalf-of tokens), in week 4.

## D-004 · 2026-10-24 · Policy term is computed from term dates and payment history, never the status field

- **Decision:** Whether the policy responds on the loss date is computed from the effective and
  expiration dates and the cancellation and reinstatement history. The PAS `status` field is shown to
  the adjuster but never drives an outcome. The policy period runs from 12:01 a.m. on the effective
  date to 12:01 a.m. on the expiration date (clause CLS-PER-006).
- **Why:** The client's own example: the status field said Active three days after the term ended,
  and the claim was paid. A cached status is a derived value; the dates are the source of truth.
- **Alternatives considered:** Trust the status field, or let the model reconcile it with the dates.
  Rejected: the first reproduces the client's bug; the second hands a date comparison to a model.
- **Owner:** FDE
- **Revisit when:** The client confirms a case where status is authoritative (open question 5 in the
  charter).

## D-005 · 2026-10-24 · Citations restricted to retrieved clause IDs

- **Decision:** The policy corpus is indexed at clause level, keyed by clause ID (for example,
  `CLS-PER-006`). The coverage agent may cite only clause IDs present in its retrieved set; a
  validator in code removes any other citation and marks the output as uncited.
- **Why:** The brief requires coverage output to cite clauses actually retrieved (area C). A model
  can produce a plausible clause ID that was never retrieved; a code check catches that every time.
- **Alternatives considered:** Trust the model's citations, or chunk by page. Rejected: the first
  allows invented citations; the second makes a citation point at a page, not the governing clause.
- **Owner:** FDE
- **Revisit when:** Clause IDs in the supplied corpus aren't stable across form revisions.

## D-006 · 2026-10-24 · Evaluation cases versioned from day one, with a held-out split

- **Decision:** Evaluation cases live in `evals/` under version control, starting with the 20 v0
  cases, and each case records its reference outcome, the deterministic values code must produce, and
  the clauses it must cite. From week 3, at least 30 cases are held out and never used while tuning
  prompts. Adversarial cases (prompt injection, cross-record leakage, forced auto-decision) are kept
  in every version.
- **Why:** Success is defined now, with the client in the room, not in week 5 to fit whatever was
  built. A held-out split is the only honest test of "claims it was not tuned against" (area C).
- **Alternatives considered:** Write the evaluation suite in week 5. Rejected: it would end up
  matching the system instead of the requirement.
- **Owner:** FDE (cases), Claims Quality Lead (labels)
- **Revisit when:** The Quality Lead disagrees with a reference label. The label changes only with a
  dated entry here.

## D-007 · 2026-10-24 · The legacy fraud score is an input, not the trigger

- **Decision:** The legacy fraud score is passed to the risk agent as one piece of evidence. ROUTE is
  decided by reading the file for inconsistencies (timeline, injuries, damage versus narrative, prior
  claims, document dates), and the reasoning must name the inconsistency. A high score with a
  consistent file isn't routed.
- **Why:** The client said threshold-based referral is part of the problem: it misses low-score fraud
  and floods SIU with high-score claims that are fine. Evaluation cases EV-005 and EV-015 test both
  directions.
- **Alternatives considered:** Keep the threshold and add model reading on top. Rejected: it keeps the
  false referrals the SIU Manager complains about.
- **Owner:** FDE, to be confirmed with the SIU Manager
- **Revisit when:** Fraud routing precision falls below 70% in evaluation.
