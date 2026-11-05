# DECISIONS.md

Engagement decision log for ClaimSense AI. One entry per real decision, newest last. Each entry
records what was decided, why, what was rejected, who owns it, and what would reopen it.

---

## D-001 Â· 2026-10-24 Â· Deterministic spine, model judgment only where reading is required

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

## D-002 Â· 2026-10-24 Â· Four outcomes with a fixed precedence; refusal is not an outcome

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

## D-003 Â· 2026-10-24 Â· Access control is code that runs before any agent

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

## D-004 Â· 2026-10-24 Â· Policy term is computed from term dates and payment history, never the status field

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

## D-005 Â· 2026-10-24 Â· Citations restricted to retrieved clause IDs

- **Decision:** The policy corpus is indexed at clause level, keyed by clause ID (for example,
  `CLS-PER-006`). The coverage agent may cite only clause IDs present in its retrieved set; a
  validator in code removes any other citation and marks the output as uncited.
- **Why:** The brief requires coverage output to cite clauses actually retrieved (area C). A model
  can produce a plausible clause ID that was never retrieved; a code check catches that every time.
- **Alternatives considered:** Trust the model's citations, or chunk by page. Rejected: the first
  allows invented citations; the second makes a citation point at a page, not the governing clause.
- **Owner:** FDE
- **Revisit when:** Clause IDs in the supplied corpus aren't stable across form revisions.

## D-006 Â· 2026-10-24 Â· Evaluation cases versioned from day one, with a held-out split

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

## D-007 Â· 2026-10-24 Â· The legacy fraud score is an input, not the trigger

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

## D-008 Â· 2026-10-27 Â· Pydantic v2 models are the contract layer; JSON Schemas are generated

- **Decision:** The typed contracts for the CMS, PAS, document store and clause corpus are Pydantic v2
  models in `src/claimsense/contracts/`. They are strict (unknown fields rejected, immutable). Money is
  a two-place `Decimal`, never a float, and VINs and names have synthetic-only patterns. The JSON
  Schemas in `data/schemas/` are generated from the models, and a test fails if they drift.
- **Why:** The same models validate client payloads at the adapter edge, type the agents' outputs, and
  publish the schemas, so there is one definition instead of three. Strictness makes a changed client
  payload fail loudly at the boundary (R1). Pydantic is also what the OpenAI Agents SDK uses for
  structured output.
- **Alternatives considered:** (a) Hand-written JSON Schema as the source, with generated classes.
  Rejected: two artifacts to keep in step, and weaker validators (no cross-field rules such as "an
  override needs a reason"). (b) Dataclasses. Rejected: no validation at the boundary.
- **Owner:** FDE
- **Revisit when:** The official fixtures arrive with their own schema; then adapters map to our
  models, rather than the models changing to match.

## D-009 Â· 2026-10-27 Â· The one write is idempotent on claim_id + run_id

- **Decision:** `POST /claims/{claim_id}/recommendations` requires `Idempotency-Key:
  {claim_id}:{run_id}`. The first request creates the draft (201). A replay with the same body
  returns the original response (200) and writes nothing. The same key with a different body returns
  409 and writes nothing. Bodies are compared by the SHA-256 of their canonical JSON. A run_id is
  never reused.
- **Why:** Agent calls are slow and retried. Without this rule, a timeout followed by a retry
  creates two drafts on one claim, and the adjuster confirms the wrong one. The 409 makes a silent
  overwrite impossible.
- **Alternatives considered:** (a) Key on claim_id alone. Rejected: a legitimate re-run after new
  documents arrive would be blocked. (b) Last write wins. Rejected: it can overwrite a draft the
  adjuster is already reviewing. (c) A server-generated key. Rejected: the client can't retry safely
  if it never saw the key.
- **Owner:** FDE; to be agreed with claims IT (the CMS owners)
- **Revisit when:** The CMS offers native idempotency, or adjusters need to amend a draft in place.

## D-010 Â· 2026-10-27 Â· Agents get a pre-fetched dossier, not tools to the client systems

- **Decision:** After entitlement passes, deterministic code fetches one claim's record, policy and
  documents, computes the deterministic facts, and hands the agents a fixed dossier. The agents have
  no tool that reaches the CMS, PAS or document store; the coverage agent's only tool searches the
  clause corpus. The architecture draws the two zones separately, and every flow between them is
  labeled.
- **Why:** The agents need one known claim, so there is nothing for a record-fetching tool to do
  except fetch the wrong record. Without such a tool, an injected instruction (EV-002, EV-008,
  EV-018) can't reach another claim, and cross-record leakage becomes structural rather than a model
  behavior. It also removes tool round trips from the 90 s latency budget.
- **Alternatives considered:** A governed MCP server between agents and systems, the Week 14
  reference pattern. Rejected for the pilot: safer than direct access, but it still gives the model
  a way to request records. Kept as the upgrade path.
- **Owner:** FDE; CISO to review at M2 sign-off
- **Revisit when:** Agents need documents the dossier can't anticipate, or the scope grows to
  multi-claim reasoning (for example, a linked-claims fraud ring).

## D-011 Â· 2026-10-27 Â· Pricing: the rate card is the bill rate; fixed floor plus a capped outcome bonus

- **Decision:** The US rate card is what the client pays: principal FDE $325/h, senior AI engineer
  $275/h, engagement manager $250/h, evaluation engineer $200/h, on an 8-hour day, blending to
  $2,180/day. The T&M price is billable days Ã— the rate card plus expenses at cost ($191,430 at
  expected effort).
  - **Cost is separate.** It is each role's loaded cost per billable hour: Levels.fyi pay at a
    boutique-firm percentile Ã· 0.70 benefits loading (BLS ECEC) Ã· 1,560 billable hours (75%
    utilization, SPI 2026). That blends to $1,318/day, a 39.5% labor gross margin.
  - **The recommended price.** A fixed floor equal to the expected T&M price ($191,430, 37.8% gross
    margin), plus $15 per recommendation the adjuster confirms unchanged during an 8-week
    post-handover production pilot, capped at 2,000.
  - **Who counts.** The count comes from `AdjusterDecisionEvent` records in the CMS audit log,
    reconciled by the Claims Quality Lead. The co-pilot's own count is never used. The numbers are in
    `scripts/pricing.py`.
- **Why:** Using the rate card as the bill rate means the client pays the market rate for the
  expected effort, no more. The rate card sits at roughly the 75th to 90th percentile of GSA CALC
  federal ceiling rates for its categories, and federal ceilings run at or below commercial prices.
  The margin comes from the gap between bill rate and cost, and lands in the 35â€“45% consulting
  range. The floor gives procurement a ceiling, and the bonus pays only for the outcome the client's
  board cares about, counted by the client.
  - **Why the first draft changed.** It put margin on top of market rates, which counted margin
    twice. It started from a single $1,800/day blended rate, then moved to marking up the rate card.
- **Alternatives considered:** (a) Pure fixed price at expected T&M Ã— 1.20 ($229,716). Rejected:
  safer for us, but a hard premium to defend while access delays are the client's. (b) Pure
  outcome-based. Rejected: with synthetic data only, no confirmation can happen before handover.
  (c) T&M with a cap. Rejected: no ceiling until the cap, and no alignment to the result.
  - **The high case.** It costs $13,320 more than the floor. SoW clause 9a bills the access
    overrun ($25,288) and turns it to +$11,968; clause 9b re-plans M5 if M3 or M4 slips.
- **Owner:** FDE; approved by the VP of Claims
- **Revisit when:** Utilization falls toward SPI's 66.4% average (labor margin drops to 31.7%), the
  team must be paid at big-tech rates (16.8%), or the production pilot isn't approved within 30
  days of handover (the bonus lapses and the floor stands alone).

## D-012 Â· 2026-10-27 Â· Planned AWS footprint; local stack first until the IK account exists

- **Decision:** Plan API Gateway, ECS Fargate, ECR, Cognito, DynamoDB (audit and idempotency), S3
  (corpus and fixtures), Secrets Manager and CloudWatch. All are marked "planned, pending IK account".
  Until then, Docker Compose runs the same container with local stand-ins.
- **Why:** The brief fixes AWS for hosting. The account isn't provisioned yet (R2), so nothing in
  weeks 2 and 3 may depend on it. These services are all in default quotas, and Fargate avoids
  Lambda's timeout and cold-start margins for 90 s agent calls.
- **Alternatives considered:** Lambda, rejected for timeout and cold-start margins. Managed
  OpenSearch, rejected as oversized for tens of clauses and a quota risk. Bedrock Agents, rejected
  because the brief standardizes on the OpenAI Agents SDK.
- **Owner:** FDE
- **Revisit when:** The IK account arrives with quotas or a budget cap that rule a service out.

## D-013 Â· 2026-10-27 Â· Synthetic values are synthetic by construction

- **Decision:** Every VIN starts `SYN`, and every person is named "Synthetic <role> NNN"; the
  contracts reject anything else. Two Milestone 1 values were changed to comply: EV-010's excluded
  driver "Jordan Vale" became "Synthetic Driver 010", and EV-019's canary VIN `1HGTEST0019CANARY`
  became `SYNTEST0019CANARY`, because `1HG` is a real manufacturer prefix.
- **Why:** "Synthetic data only" is a fixed constraint. A realistic name or a real manufacturer
  prefix is indistinguishable from leaked data in a log or a screenshot. A validator makes the rule
  checkable instead of a matter of care.
- **Alternatives considered:** Realistic fake names, as faker libraries generate. Rejected: they
  collide with real people.
- **Owner:** FDE
- **Revisit when:** The official fixtures use a different convention; then the patterns follow theirs.

## D-014 Â· 2026-10-27 Â· The eval cases are the source of the synthetic fixtures

- **Decision:** `scripts/build_fixtures.py` generates `data/synthetic/` from `evals/cases_v0.yaml`,
  validating every record against the contracts. A fixture changes only by changing the case and
  rebuilding, and a test fails if the files are stale.
- **Why:** If fixtures and eval cases are written separately, they drift, and the system ends up
  tested on data it was never run on. One source keeps them identical.
- **Alternatives considered:** Hand-written fixture files. Rejected: a second copy of every fact.
- **Owner:** FDE
- **Revisit when:** The instructor's official fixtures arrive; they become the source, and the eval
  cases reference them by ID.
## D-015 Â· 2026-10-31 Â· Outcome mapping to the instructor's labels; eval set to 5 per outcome

- **Decision:** Our four outcomes map one to one onto the instructor's Week 1 labels:

  | Ours | Instructor's | Meaning here |
  |---|---|---|
  | APPROVE | `approve` | covered, no specialist handling; code computes the payable |
  | DENY | `deny` | the policy doesn't respond |
  | FLAG | `flag_review` | a licensed adjuster must handle it first: injury, likely total loss, missing documents |
  | ROUTE | `route_specialist` | **SIU only**: fraud indicators in the file |
  | REFUSED (not an outcome) | `reject`, RBAC violation (403) | unentitled request, refused in code before any agent runs |

- **Two deliberate differences from the instructor's examples:**
  - **Total loss.** The instructor's guide routes a total loss to a total-loss appraiser as
    `route_specialist`. Here ROUTE means SIU and nothing else, and a total loss is FLAG (EV-012,
    EV-021). That keeps fraud routing precision (success criterion 4) measurable on one population.
  - **Prompt injection.** The guide rejects an injected request outright ("guardrail fires"). Here
    the claim is still decided on its own facts, the injected text is treated as evidence and noted
    as a finding, and the injection never changes the outcome (EV-002, EV-008, EV-018). Rejecting the
    whole claim would let any claimant block their own adjudication with one sentence.
- **The eval set** grows to the instructor's split: 5 APPROVE, 5 DENY, 5 FLAG, 5 ROUTE, plus the 2
  refused-access cases (22 in total). EV-021 is a total-loss boundary case at exactly 0.75 with a
  forced-auto-decision request (adversarial). EV-022 is a document-timeline fraud case the legacy
  score misses. Every case now carries `expected_reasoning` (one sentence) and
  `minimum_confidence`: high for clear and adversarial cases, medium for the 5 edge cases where the
  outcome rests on judgment.
- **Why:** The instructor's checklist and eval-case template use these labels and this split. A
  documented mapping lets the instructor read our results in their terms without renaming outcomes
  that the contracts, checker and success criteria already use.
- **Also fixed:** a quoting bug found while adding the fields. Document summaries and findings that
  contained a comma sat unquoted inside YAML flow mappings and lists, so the parser cut them at the
  first comma. 19 summaries were truncated, and the Milestone 2 fixtures inherited the truncated text.
  All are now quoted, and the checker fails if a summary or finding is ever split again.
- **Alternatives considered:** Renaming our outcomes to the instructor's labels. Rejected: it churns
  the contracts, fixtures and every document for no change in meaning.
- **Owner:** FDE; total-loss and SIU routing to be confirmed with the Claims Quality Lead and SIU Manager
- **Revisit when:** The client wants total losses routed to an appraiser queue distinct from
  adjuster review; then a sixth label is added, and criterion 4 stays SIU-only.

## D-016 Â· 2026-10-31 Â· The four agents use the instructor's names

- **Decision:** The agents are Document Intake, Coverage Check, Claim Assessment and Decision Draft,
  in that order, in the charter, the architecture diagram and the risk register. They were
  previously File reader, Coverage, Risk and Drafter. Responsibilities are unchanged.
  - **Where the scope differs from the instructor's description.** Coverage Check judges coverage
    from clause wording only, and the net payable stays in code (D-001), where the instructor's
    version also calculates it. Claim Assessment treats the legacy fraud score as one input, never the
    trigger (D-007).
- **Why:** One vocabulary across the course materials, the reviews and this repo, so a reader moves
  between them without a translation table.
- **Alternatives considered:** Keep our own names. Rejected: no benefit, and a translation cost for
  every reviewer.
- **Owner:** FDE
- **Revisit when:** Never for the pilot.
## D-017 Â· 2026-11-04 Â· Four typed agents; gpt-4o-mini reads, gpt-4o decides what the wording means

- **Decision:** Document Intake and Claim Assessment run on `gpt-4o-mini`; Coverage Check and Decision
  Draft run on `gpt-4o`. All four are OpenAI Agents SDK agents with a strict Pydantic `output_type`.
  Coverage Check and Claim Assessment run in parallel after Document Intake.
- **Why:** The routing was set by the engagement lead. It puts the expensive model where a wrong
  reading is a wrongful denial or payment, and keeps volume reading cheap. On the first live run
  gpt-4o took 93% of the cost: about $0.019 per claim in total. Parallel stages protect the latency
  budget (R5).
- **Alternatives considered:** (a) gpt-4o everywhere. Rejected on cost, without evidence yet that it
  would be more accurate. (b) One agent. Rejected in Milestone 2: errors can't be attributed to a stage.
- **Owner:** FDE
- **Revisit when:** A stage's errors dominate. The first live run points at Claim Assessment on
  gpt-4o-mini, where all three fallbacks occurred. That is one run, and it is not yet a finding about
  the model rather than the prompt or the turn limit.

## D-018 Â· 2026-11-04 Â· The mock brain is an SDK Model, and it proves plumbing, not judgment

- **Decision:** `MockModel` implements the Agents SDK's `Model` interface, so CI runs the real `Agent`,
  `Runner`, strict output validation and tool loop, with no key and no network. It reads the claim
  file with plain text rules, never sees a reference label, and contains no case or claim IDs (a test
  checks this). CI's gate runs on it.
- **Why:** A gate that needs a key flakes, and a stub that skipped the SDK wouldn't test the seam where
  typed output and tool calls actually break. It also forces every failure path through the real SDK.
- **The limit, stated plainly:** Its rules were written with the evaluation scenarios in view, so its
  100% on v0 proves the pipeline, guardrails and gate work. It says nothing about model judgment. **A
  green gate does not mean the models meet the acceptance criteria.** The first live run scored 70% on
  the same cases the mock scored 100% on. Reports state which brain produced them.
- **Alternatives considered:** A lookup table of recorded answers per case. Rejected: it would pass any
  label it was recorded against, and it would leak labels into the pipeline.
- **Owner:** FDE
- **Revisit when:** The live gate in Milestone 5 ("the gate passes with the model required") replaces
  the mock as the release gate. The mock stays for pull requests.

## D-019 Â· 2026-11-04 Â· BM25 retrieval, seeded by code; Claim Assessment also gets the search tool; any invented citation marks the output uncited

- **Decision:**
  - **Index.** A local BM25 index over the corpus, keyed by clause ID, with ties broken by clause ID.
  - **Seeding.** Code runs three seed searches per claim (policy period, declarations, the insuring
    agreement for the loss type), so a code-computed DENY can always cite its clause.
  - **Tool scope.** Claim Assessment now holds `search_clauses` too. This widens D-010, which gave it
    only to Coverage Check, because fraud, injury and total-loss conclusions rest on clauses as well.
    The tool still returns only policy wording, scoped to the claim's form.
  - **Validator.** Every citation is checked against the clauses retrieved in this run. Anything else
    is removed and the output is marked uncited, even if valid citations remain.
  - **Consequence.** An uncited APPROVE or model DENY goes to FLAG. A code-computed DENY and a ROUTE
    stand.
- **Why:** Deterministic retrieval runs in CI with no key and can be tested exactly. A model that
  invents one clause ID shouldn't be trusted on the others without an adjuster looking, which is the
  Week 15 "safely escalated" pattern.
- **Alternatives considered:** (a) Embeddings. Rejected for tens of clauses: they add a key to CI and
  nondeterminism, for no measured gain. (b) Marking uncited only when no citation survives. Rejected:
  it hides an invented citation.
- **Owner:** FDE
- **Revisit when:** The official corpus arrives and BM25 misses clauses that adjusters consider
  governing, or `must_cite` recall stays low on it (20 of 24 on the first live run).

## D-020 Â· 2026-11-04 Â· Verdict source, fallback, and what counts as a hit

- **Decision:**
  - **Label.** Every response carries `verdict_source`, `model` or `deterministic_fallback`.
  - **When the fallback runs.** If a model is unavailable, times out, returns invalid output, or its
    output names another claim. It can only DENY on a term or coverage failure, or FLAG. It never
    approves or routes, carries no judgment block, and names no model.
  - **Scoring.** A hit needs a model verdict whose drafted outcome equals the label. A fallback is a
    miss. If code raised the draft to the right answer, the case is also a miss: the override is
    reported, and "accuracy after code" is shown separately and never credited.
- **Why:** Success criterion 1 measures model-generated outcomes, and the rubric treats fallback-only
  outcomes as Weak. On the first live run strict accuracy was 70% against 80% after code; reporting the
  higher number would have credited the models for what code did.
- **Alternatives considered:** Counting the final outcome only. Rejected for that reason.
- **Owner:** FDE
- **Revisit when:** The client wants system accuracy as the contractual measure. The SoW says
  model-generated today.

## D-021 Â· 2026-11-04 Â· Six held-out claims in v0; the eval gate's rules; D-006's 30 moves to week 5

- **Decision:**
  - **Split.** Each case now has a `split`. Six decision cases are held out: EV-004, EV-007, EV-010,
    EV-017, EV-021 and EV-022. Refusal cases aren't held out, because they don't exercise judgment.
  - **Gate.** It fails on decision accuracy below 85%, held-out accuracy below 80%, any failed
    adversarial or access-control case, or any guardrail breach. The last two floors come from the
    success criteria; the rest were set by the engagement lead. Fraud routing, `must_cite` and minimum
    confidence are reported but not gated yet.
- **Deviation from D-006:** D-006 promised at least 30 held-out cases from week 3. The suite has 22
  cases, so 30 isn't possible until the suite grows in week 5. Six is the honest number today, and with
  six a single miss moves the score by 17 points.
- **How held out these really are:** The author wrote all 22 cases, so nothing is hidden from the
  author. The discipline is narrower: no prompt carries a case, and held-out results aren't used to
  tune prompts. The mock brain's rules were written with all 22 in view, so its held-out score means
  nothing; only the live one counts.
- **After the first live run:** EV-004 and EV-022 missed. Their failures were looked at only as far as
  outcome, stage, override and missing citations. Fixing either would make that case no longer held out, so any such fix
  must retire it from the held-out set.
- **Alternatives considered:** Writing 30 new cases now. Rejected: out of scope this week, and the live
  run was limited to the 22.
- **Owner:** FDE; Claims Quality Lead for labels
- **Revisit when:** Week 5, when the suite reaches 150 cases.

## D-022 Â· 2026-11-04 Â· CI order, and how the block is proved

- **Decision:** `tests` -> `eval-gate` -> `build-and-push-image`. The image job `needs` the gate. It
  starts the stack with compose, smoke-tests a real request through the containers, and pushes to GHCR
  only on a push to `main`.
- **Why the image job also runs on pull requests:** If it ran only on `main`, a skipped push on a pull
  request would prove nothing, because the branch condition alone would skip it. Running it on pull
  requests gives a real comparison: a green pull request shows the job running with only the push step
  skipped, and a red one shows the whole job skipped because the gate failed.
- **Why the broken case swaps two labels:** The broken case has to pass `pytest` and fail the gate, or
  the run proves the tests block rather than the gate. Pipeline tests therefore hard-code their expected
  outcomes instead of reading labels from the YAML.
- **Not done:** Branch protection isn't turned on, so a person could still merge over a red check. The
  push is blocked regardless. Making the gate a required check is a repository setting for the owner.
- **Alternatives considered:** Copying the course's `eval-gate.yml` as is. Rejected: it gates merges but
  not image pushes, which this milestone requires.
- **Owner:** FDE
- **Revisit when:** Milestone 5 adds the live gate and a deploy step.

## D-023 Â· 2026-11-04 Â· Milestone 3 identity is a placeholder; the entitlement check is not

- **Decision:** The API takes the caller's identity from an `X-User-Id` header, unverified. Entitlement
  against the CMS assignment is real, and runs before anything else is fetched or any agent is invoked.
  Mock client systems have no authentication, and compose publishes only the co-pilot's port. The audit
  log is in memory and written to the service log.
- **Why:** Token verification and durable audit are Milestone 4 deliverables. Getting the order of
  operations right now means Milestone 4 replaces one input rather than restructuring the pipeline.
- **Risk accepted:** Anyone who can reach port 8000 can claim to be any user. **This service must not
  be exposed before Milestone 4.** Nothing here is deployed.
- **Alternatives considered:** A hard-coded demo token. Rejected: it looks like authentication without
  being it.
- **Owner:** FDE; CISO at the Milestone 4 sign-off
- **Revisit when:** Milestone 4.
