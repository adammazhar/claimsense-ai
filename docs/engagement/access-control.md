# ClaimSense AI: Access-Control Matrix

Milestone 4, 2026-11-11. All data is synthetic. Enforced in code by the MCP door
(`src/claimsense/door/scope.py`) and, underneath it, by the CMS's own row filter. Prompts are advisory
and enforce nothing. Decisions: D-031 to D-038.

## Who can see what

Deny by default: any role not listed here, an unknown token, a revoked seat and an expired seat all get
nothing.

| Seat role | Claims in scope | SIU referral (fraud details) | Write the draft | Example seat |
|---|---|---|---|---|
| `adjuster_pd` | Physical-damage claims **assigned to the seat** | Stripped | Claims in scope | `adj-001` |
| `adjuster_bi` | Bodily-injury claims **assigned to the seat** | Stripped | Claims in scope | `adj-004` |
| `siu` | Claims with an open SIU referral | Visible | Claims in scope | `siu-001` |
| `supervisor` | Every claim | Visible | Claims in scope | `sup-001` |
| any other role (e.g. `customer_service`) | None | n/a | No | `cs-021` |
| no token, unknown, revoked or expired | None: 401 before any tool runs | n/a | No | |

- **The claim line** (`physical_damage` or `bodily_injury`) is a stored CMS field, set at first notice
  of loss. It is never inferred, and never shown to a model.
- **A refused request** returns `403 forbidden_scope`, whether or not the claim exists. Only a
  supervisor gets `404 not_found` for a claim that doesn't exist.
- **No tool takes an identity argument.** The door learns the seat from the bearer token, so a model
  can't set or forge it.

## What enforces it

| Layer | Where | What it does | Test |
|---|---|---|---|
| Token check | Door transport (`SeatVerifier`) | Resolves the token to a seat; 401 otherwise, audited | `test_door_identity.py` |
| Scope gate | Door, on every tool call | Allows or denies by the matrix above; audits the decision | `test_scope_matrix.py` |
| Row filter | CMS (`mock_services`) | Refuses rows outside the acting seat; strips fraud details | `test_data_layer_filter.py` |
| Network | Compose `backend` network | Only the door can reach the systems of record | `test_no_direct_backend.py`, CI |
| Prompt | Agent instructions | Advisory only | `test_jailbreak.py` (ignored by a jailbroken model, and still refused) |

## Door tools

| Tool | Reaches | Called by |
|---|---|---|
| `get_claim(claim_id)` | CMS claim and assignment | Pipeline code: the gate's first call |
| `get_policy(claim_id)` | PAS, as of the loss date | Pipeline code |
| `get_claim_documents(claim_id)` | Document store | Pipeline code |
| `search_clauses(claim_id, query)` | Clause library, on the claim's form | Coverage Check and Claim Assessment, the only model tool. Code binds `claim_id` to the request's claim; one a model names anyway goes to the gate |
| `submit_draft_recommendation(claim_id, idempotency_key, draft)` | CMS, the one write | Pipeline code |
| `whoami()` | Seat registry | Pipeline code |

## Audit

Every call writes one row, before it returns, to `runtime/audit.jsonl`:
`ts, request_id, correlation_id, acting_identity, role, scope, action, resource, decision, reason`, plus
a hash chain. A sample is in [docs/evidence/m4](../evidence/m4/README.md).
