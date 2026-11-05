# ClaimSense AI: Client-System Contracts

Typed input and output contracts for the three client systems and the policy clause corpus. The
**Pydantic v2 models in [`src/claimsense/contracts/`](../../src/claimsense/contracts/) are the source
of truth** (D-008). The JSON Schemas in [`data/schemas/`](../../data/schemas/) are generated from them
by `scripts/generate_schemas.py`, and `pytest` fails if the two drift apart.

**Every model is strict.** Unknown fields are rejected and instances are immutable, so a change in a
client payload fails at the adapter instead of leaking into the pipeline.

**Values are exact.** Money is a `Decimal` with two places, serialized as a string (`"2400.00"`),
never a float. Identifiers have fixed patterns, and VINs and people's names have **synthetic-only**
patterns: VINs start `SYN`, and names are `Synthetic <role> NNN`. A real-looking value fails
validation (`tests/test_contracts.py`).

The endpoints are the integration points named in the [charter](../engagement/charter.md). The
co-pilot reaches them only through the data-access service, using its own service credential, and
only after the caller's entitlement has been checked (D-003).

## Errors (all endpoints)

Any non-2xx status returns `ErrorResponse {code, message, request_id, retryable}`.

| Status | `code` | Meaning | Retryable |
|---|---|---|---|
| 400 | `IDEMPOTENCY_KEY_MISSING`, `IDEMPOTENCY_KEY_MISMATCH` | write without, or with a wrong, Idempotency-Key | no |
| 401 | `UNAUTHENTICATED` | missing or invalid service credential | no |
| 403 | `FORBIDDEN` | credential valid but not allowed this operation | no |
| 404 | `NOT_FOUND` | no such claim, policy or document | no |
| 409 | `IDEMPOTENCY_CONFLICT` | key reused with a different body | no |
| 422 | `VALIDATION_FAILED` | request failed schema validation | no |
| 429 | `RATE_LIMITED` | back off and retry | **yes** |
| 503 | `UPSTREAM_UNAVAILABLE` | system of record down | **yes** |

**Two error rules matter for the trust boundary.**

- **A refusal reveals nothing.** When the *caller* isn't entitled, the co-pilot's own API returns the
  same refusal whether or not the claim exists. EV-019 must not reveal "whether the claim exists".
  That refusal comes from the data-access service, before any client system is called.
- **Errors fail closed.** If a client-system call fails after retries, the pipeline stops for that
  claim and returns an error, never a decision made on partial data.

## Claims management system (CMS): `cms.py`

| Operation | Request | Response | Errors |
|---|---|---|---|
| `GET /claims/{claim_id}` | `GetClaimRequest {claim_id}` | `Claim` | 401, 404, 429, 503 |
| `GET /claims/{claim_id}/assignment` | `GetClaimRequest {claim_id}` | `ClaimAssignment` | 401, 404, 429, 503 |
| `POST /claims/{claim_id}/recommendations` | header `Idempotency-Key`, body `DraftRecommendationRequest` | `DraftRecommendationResponse`: 201 created, 200 replay | 400, 401, 409, 422, 429, 503 |

**`Claim`:** `claim_id`, `policy_id`, `loss_datetime` (local time at the loss location, which the
policy-period clause uses), `loss_type` (collision, comprehensive or theft), `narrative`, `vehicle`
(synthetic VIN, year, make, model), `claimant` (party ID, synthetic name), `repair_estimate`,
`legacy_fraud_score` (an input only, D-007), `prior_claims_24m` and `reported_at`.

**`ClaimAssignment`:** `claim_id`, `adjuster_user_id`, `desk` and `assigned_at`. This is the source of
truth for entitlement.

**`DraftRecommendationRequest`, the only write:**
- **`claim_id` and `run_id`** (a UUID), which together are the idempotency key.
- **`outcome`:** APPROVE, DENY, FLAG or ROUTE.
- **`verdict_source`:** `model` or `deterministic_fallback`, so model verdicts are distinguishable
  (brief, Milestone 3).
- **`confidence`:** high, medium or low.
- **`reasoning`.**
- **`deterministic`:** in term, coverage present, total-loss ratio, total-loss candidate, days since
  inception, photos before inception, payable.
  These are computed in code and shown apart from the judgment.
- **`findings`:** each one must cite at least one document or clause. A model verdict needs at least
  one, or must be marked uncited.
- **`cited_clause_ids`:** only from the retrieved set. May be empty only when `uncited` is true.
- **`uncited`:** true if the validator removed a citation or none remain (D-019).
- **`model_ids` and `requested_by`.**

There is **no status field in the request**: the co-pilot can only create a `draft`, which is how
EV-014's "mark it final" is made impossible by construction.

**`AdjusterDecisionEvent`:** emitted by the CMS, not the co-pilot, when the adjuster acts. It carries
`action` (confirmed or overridden), `override_reason` (required exactly when overridden),
`final_outcome` and `occurred_at`. Success criterion 3 and the pricing outcome bonus are counted from
these events (D-011).

### The idempotency rule for the write (D-009)

1. **The key** is `claim_id` + `run_id`, sent as the header `Idempotency-Key: {claim_id}:{run_id}`.
   If the header is missing, the response is **400 `IDEMPOTENCY_KEY_MISSING`**. If it doesn't match
   the path and the body, the response is **400 `IDEMPOTENCY_KEY_MISMATCH`**.
2. **First request** with the key: the draft is created and the response is **201**. The response is
   stored with a SHA-256 fingerprint of the canonical JSON body (sorted keys, no whitespace).
3. **Replay** (same key, same fingerprint): **200 with the original response**, and no second draft is
   created. A retry after a timeout is always safe.
4. **Same key, different body:** **409 `IDEMPOTENCY_CONFLICT`**, and nothing is written. A changed
   recommendation needs a new `run_id`, which creates a new draft.
5. **Keys are kept for the life of the claim**, and a `run_id` is never reused.

The reference behavior is `IdempotencyStore` in
[`idempotency.py`](../../src/claimsense/contracts/idempotency.py), tested in
`tests/test_idempotency.py`. The deployed version is a DynamoDB conditional write (planned, D-012).

## The co-pilot API: `copilot.py`

`POST /v1/claims/{claim_id}/recommendation`, with the header `X-User-Id` (a Milestone 3 placeholder,
D-023) and an optional body `RecommendRequest {note, run_id}`. Retrying with the same `run_id` returns
the original result without rerunning the agents, after rechecking entitlement.

| Status | Meaning |
|---|---|
| 200 | `RecommendationResponse` |
| 401 | no identity supplied |
| 403 | not entitled; the same body whether or not the claim exists |
| 409 | this `run_id` is already held by the CMS with a different body |
| 503 | a client system failed or broke its contract; no decision was made |

`RecommendationResponse` keeps attribution visible in every response: `deterministic` comes from code,
`judgment` comes from the model and is null on a fallback, `verdict_source` with `fallback_reason`,
`fallback_stage` and `fallback_error` says which produced the verdict, and `code_overrides` records
every place code changed what the model drafted. It also carries `citations_removed`, `uncited`,
`injection_flags`, per-stage `usage` and a `trace_id`.

## Policy administration system (PAS): `pas.py`

| Operation | Request | Response | Errors |
|---|---|---|---|
| `GET /policies/{policy_id}?as_of={loss_date}` | `GetPolicyRequest {policy_id, as_of}` | `Policy` | 401, 404, 422, 429, 503 |

**`Policy` fields:**
- **Identity and form:** `policy_id`, `as_of`, `form_number` (selects the clause wording), and the
  named insured (party ID, synthetic name).
- **Term:** `effective_date` and `expiration_date`, validated so the expiration comes after the
  effective date.
- **`status_field`:** display only (D-004).
- **`transactions`:** issued, missed payment notice, payment received, canceled, reinstated, renewed.
- **`coverages`:** keyed by liability, collision, comprehensive or medical payments, each with a
  deductible and a limit.
- **`endorsements`:** an excluded-driver endorsement must name the driver.
- **`vehicle_acv`.**

Code computes "in term" from the dates and transactions under CLS-PER-006: from 12:01 a.m. local time
on the effective date to 12:01 a.m. on the expiration date.

## Document store: `documents.py`

| Operation | Request | Response | Errors |
|---|---|---|---|
| `GET /claims/{claim_id}/documents` | `ListDocumentsRequest {claim_id}` | `DocumentList {claim_id, documents: [DocumentMeta]}` | 401, 404, 429, 503 |
| `GET /documents/{doc_id}` | `GetDocumentRequest {doc_id}` | `Document {meta, text}` | 401, 404, 429, 503 |

**`DocumentMeta`:** `doc_id`, `claim_id`, `type`, `received_at`, `captured_on` and `sha256`.
- **`captured_on`** comes from photo metadata. Code compares it with policy inception, which is how
  EV-017's photos dated before the policy began are caught.
- **`sha256`** pins the text that a citation points at.

**Document text is untrusted.** It is passed to agents as quoted evidence, never as instructions.

## Policy clause corpus: `corpus.py`

Not a client system: the corpus is the searchable set of policy form wordings, indexed by clause (D-005).

| Shape | Fields |
|---|---|
| `ClauseEntry` | `clause_id` (`CLS-XXX-NNN`), `form_number`, `form_edition`, `section`, `heading`, `text`, `tags`, `supersedes` |
| `RetrievalQuery` | `query`, `form_number`, `top_k` (1–20, default 5) |
| `RetrievalResult` | `query`, `hits: [RetrievalHit {clause_id, score, heading, text}]`; hits are unique by clause ID |

The citation validator keeps only IDs in `RetrievalResult.retrieved_ids()`.

## Synthetic data shapes

| Location | What it holds |
|---|---|
| `data/schemas/*.schema.json` | 18 JSON Schemas, one per published model |
| `data/synthetic/claims.json` | 21 claims (EV-020 reuses EV-001's claim) |
| `data/synthetic/assignments.json` | 21 assignments |
| `data/synthetic/policies.json` | 21 policies |
| `data/synthetic/documents.json` | 45 documents |
| `data/synthetic/clauses.json` | 11 clauses, covering every clause ID the eval cases cite |

The fixtures are **generated from `evals/cases_v0.yaml`** by `scripts/build_fixtures.py`, so the
fixtures and the eval cases can't disagree (D-014). The tests check four things:
- Every record validates against its contract.
- The files match a fresh build.
- References resolve (claim → policy, document → claim, cited clause → corpus).
- The fixtures reproduce the eval cases' deterministic values and entitlement.

The claims, the clause wording and the clause IDs are **placeholders** until the instructor's official
fixtures and corpus arrive (R1). At that point only the adapters and the builder change.
