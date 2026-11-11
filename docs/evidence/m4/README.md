# Milestone 4 evidence: integration and access control

2026-11-11. All data is synthetic. Branch `m4-integration`. Decisions D-031 to D-039; the matrix is in
[access-control.md](../../engagement/access-control.md), and the diagram in
[mcp-door.md](../../architecture/mcp-door.md).

> The official W16 assignment instructions haven't been released yet. This index is built to the
> acceptance criteria on the W16 slides (p.14, p.18) and the brief's Milestone 4 list. The graded
> checklist the slides name (`lab/milestone-M3-integration.md`) isn't available, so the shape of this
> page is a guess and is kept easy to reshape.

## The three acceptance criteria

| Criterion | Evidence |
|---|---|
| 1. The agents reach client systems only through one governed MCP server that bridges at least 2 systems | The door bridges 4: CMS, PAS, document store, clause library (D-031). The co-pilot imports no client adapter and names no backend URL (`test_no_direct_backend.py`), and in compose it can't reach them: CI's `build-image` job checks that the co-pilot container can't connect to the CMS. |
| 2. Per-user scope enforced in a deterministic layer in the MCP server, never in prompts; every call audited; a denial logged before its error | The gate is `door/scope.py`; the matrix test is `test_scope_matrix.py`; the jailbreak test is `test_jailbreak.py`; with the gate removed, the CMS row filter still refuses (`test_data_layer_filter.py`). Audit: [audit-sample.jsonl](audit-sample.jsonl), and `test_audit.py` checks deny-before-error, append-only and the hash chain. |
| 3. A two-adjuster test passes in our docker compose deployment | [two-adjuster-live.txt](two-adjuster-live.txt) (real models) and [two-adjuster-mock.txt](two-adjuster-mock.txt): the same request to the co-pilot API as `adj-004` (BI) and `adj-001` (PD). It returns 200 with the co-pilot's answer (FLAG, model verdict), and 403 `forbidden_scope`, with the matching `get_claim` allow and deny rows. The CI `build-image` job repeats it on every run. |

## The files

| Deliverable | File |
|---|---|
| Test suite | [pytest.txt](pytest.txt): 289 passed |
| Mock gate, through the door | [mock-gate-run.txt](mock-gate-run.txt), [mock-gate-report.json](mock-gate-report.json) |
| Live gate, through the door | [live-gate-run.txt](live-gate-run.txt), [live-gate-report.json](live-gate-report.json) |
| Two-adjuster test, compose stack | [two-adjuster-live.txt](two-adjuster-live.txt), [two-adjuster-mock.txt](two-adjuster-mock.txt) |
| Audit sample | [audit-sample.jsonl](audit-sample.jsonl): the trail from both two-adjuster runs. Its hash chain verifies. No token appears in it. |
| Workflow lint | actionlint on `.github/workflows/ci.yml`: no findings (run locally by the engagement lead, 2026-11-11) |
| CI run on the PR | _to add once the PR's checks finish_ |

## The result

| Measure | Target | Live, through the door (run 5) | Milestone 3 |
|---|---|---:|---:|
| Decision accuracy | ≥ 85% (bar: 100%) | **100% of 22** | 100% of 22 |
| Held-out | ≥ 80% (bar: 100%) | **100% of 6** | 100% of 6 |
| Fallback verdicts | 0 | **0** | 0 |
| Adversarial | all | **8/8** | 7/7 |
| Access control | all | **3/3** (EV-025 is new) | 2/2 |
| Guardrails | each 0 | **0** | 0 |

The case file is 25 cases: 22 decision cases (6 held out), plus 3 access-control cases. Only the
access-control count changed, so the accuracy denominator matches Milestone 3 (D-038).

An uncited verdict now counts as a miss even when its outcome is right (D-040). Run 5 and the mock gate
had no uncited output, so the numbers above are the same under the old rule and the new one.

## How the live number moved

Each row is one live run of the full suite. Nothing was rerun to pick a better result.

| Run | Change since the row above | Accuracy | Held-out | Gate | Cost |
|---|---|---:|---:|---|---:|
| [1](live-run-1.txt) | Agents on the door through `Agent(mcp_servers=[...])` | 90.9% | 83.3% | pass, under the bar | $0.68 |
| [2](live-run-2.txt) | The door's search wrapped so the result reaches the model as a plain string | 90.9% | 83.3% | fail: adversarial EV-018 | $0.62 |
| [3](live-run-3.txt) | `claim_id` bound by code, not shown to the model | 95.5% | 100% | fail: adversarial EV-018 | $0.71 |
| [4](live-run-4.txt) | A Coverage Check prompt bullet (reverted after this run) | 95.5% | 83.3% | pass, under the bar | $0.69 |
| [control](live-control-m3-code.txt) | The unchanged Milestone 3 code (`main`), the same day | 100% | 100% | pass | $0.71 |
| **[5](live-gate-run.txt)** | The model-facing tool byte-identical to Milestone 3's; the prompt bullet removed | **100%** | **100%** | **pass** | **$0.73** |

**What the runs found.** Every miss in runs 1 to 4 was the same pattern: Coverage Check answered without
searching the clauses, then cited an endorsement's form number or misread a fraud inconsistency as no
coverage, and code correctly overrode the draft. Coverage Check skipped its search on 7 to 11 cases a
run, against 4 in Milestone 3. The control run ruled out model drift. The cause was the tool definition
the model saw:
- the SDK's MCP path packs the result as content items, not a string;
- the schema carried server-side keywords;
- there was a required `claim_id` argument;
- the schema lacked the SDK's `title` keys.

Run 5's coverage-stage input is byte-identical to Milestone 3's, and its search count is back to 4
(D-032). No prompt changed in this milestone, and no held-out case's content informed a fix.

## Cost

| | Cost |
|---|---:|
| Live gate runs 1 to 5 | $3.43 |
| Control run (Milestone 3 code) | $0.71 |
| Live two-adjuster run | $0.03 |
| **Local total, 2026-11-11** | **$4.18** |
| A live gate run (run 5) | $0.73, $0.033 per claim |

The CI live gate on the PR will add about $0.73, and again on the merge to `main` (D-030).

## Identity and the AWS account

- Seat tokens are minted by `scripts/issue_seat_tokens.py`. Only hashes are stored, in the
  git-ignored `runtime/`; the tokens live in the git-ignored `.env`. CI mints throwaway tokens per run.
  The production form is OIDC with RFC 8693 token exchange, or AgentCore Identity (D-033).
- The IK lab AWS account was granted S3 and Bedrock access on 2026-11-11, which closes R2's AWS
  blocker. Bedrock is a production option only; the models stay on OpenAI (D-039).

## Reproduce

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts\check_eval_cases.py
.\.venv\Scripts\python.exe scripts\run_evals.py                    # mock gate, through the door
.\.venv\Scripts\python.exe scripts\issue_seat_tokens.py            # once: seat tokens for compose
docker compose up --build --wait
.\.venv\Scripts\python.exe scripts\two_adjuster_test.py --brain mock
$env:BRAIN='openai'; docker compose up --wait                     # live: costs a few cents
.\.venv\Scripts\python.exe scripts\two_adjuster_test.py --brain openai
```
