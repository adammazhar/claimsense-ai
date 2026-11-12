# Milestone 4 evidence: integration and access control

2026-11-11 and 12. All data is synthetic. Merged to `main` in
[PR #7](https://github.com/adammazhar/claimsense-ai/pull/7) (merge commit `d9df0ba`). Decisions D-031 to
D-042; the matrix is in
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
| Test suite | [pytest.txt](pytest.txt): 291 passed |
| Mock gate, through the door | [mock-gate-run.txt](mock-gate-run.txt), [mock-gate-report.json](mock-gate-report.json) |
| Live gate, through the door | [live-gate-run.txt](live-gate-run.txt), [live-gate-report.json](live-gate-report.json) (run 6b); [live-run-6a.txt](live-run-6a.txt) |
| Two-adjuster test, compose stack | [two-adjuster-live.txt](two-adjuster-live.txt), [two-adjuster-mock.txt](two-adjuster-mock.txt) |
| Audit sample | [audit-sample.jsonl](audit-sample.jsonl): the trail from both two-adjuster runs. Its hash chain verifies. No token appears in it. |
| Workflow lint | actionlint on `.github/workflows/ci.yml`: no findings (run locally by the engagement lead, 2026-11-11) |
| CI run on the PR | [PR #7](https://github.com/adammazhar/claimsense-ai/pull/7), final run [43129923917](https://github.com/adammazhar/claimsense-ai/actions/runs/43129923917) on `8eebe5e`: `tests`, `eval-gate`, `build-image` (two-adjuster test and the network check, on the containers) and `live-eval-gate` all pass, under the pipefail shell (D-041). Live gate: 100% of 22, held-out 100% of 6, 0 fallbacks, 8/8 adversarial, $0.73. The audit trail and transcript are in the run's `two-adjuster` artifact. |
| CI run on `main` | [Run 43130785463](https://github.com/adammazhar/claimsense-ai/actions/runs/43130785463) on merge commit `d9df0ba`: all six jobs pass, including `push-image`. Live gate: 100% of 22, held-out 100% of 6, 0 fallbacks, 8/8 adversarial, $0.73. See [The image](#the-image). |

## The result

| Measure | Target | Live, through the door (runs 6a and 6b) | Milestone 3 |
|---|---|---:|---:|
| Decision accuracy | ≥ 85% (bar: 100%) | **100% of 22** | 100% of 22 |
| Held-out | ≥ 80% (bar: 100%) | **100% of 6** | 100% of 6 |
| Fallback verdicts | 0 | **0** | 0 |
| Adversarial | all | **8/8** | 7/7 |
| Access control | all | **3/3** (EV-025 is new) | 2/2 |
| Guardrails | each 0 | **0** | 0 |

The case file is 25 cases: 22 decision cases (6 held out), plus 3 access-control cases. Only the
access-control count changed, so the accuracy denominator matches Milestone 3 (D-038).

An uncited verdict now counts as a miss even when its outcome is right (D-040). Runs 5, 6a and 6b and
the mock gate are scored under that rule.

## How the live number moved

Each row is one live run of the full suite. Nothing was rerun to pick a better result.

| Run | Change since the row above | Accuracy | Held-out | Gate | Cost |
|---|---|---:|---:|---|---:|
| [1](live-run-1.txt) | Agents on the door through `Agent(mcp_servers=[...])` | 90.9% | 83.3% | pass, under the bar | $0.68 |
| [2](live-run-2.txt) | The door's search wrapped so the result reaches the model as a plain string | 90.9% | 83.3% | fail: adversarial EV-018 | $0.62 |
| [3](live-run-3.txt) | `claim_id` bound by code, not shown to the model | 95.5% | 100% | fail: adversarial EV-018 | $0.71 |
| [4](live-run-4.txt) | A Coverage Check prompt bullet (reverted after this run) | 95.5% | 83.3% | pass, under the bar | $0.69 |
| [control](live-control-m3-code.txt) | The unchanged Milestone 3 code (`main`), the same day | 100% | 100% | pass | $0.71 |
| [5](live-run-5.txt) | The model-facing tool byte-identical to Milestone 3's; the prompt bullet removed | 100% | 100% | pass | $0.73 |
| CI, PR #7 | Run 5's code ([43123372074](https://github.com/adammazhar/claimsense-ai/actions/runs/43123372074)) | 100% | 100% | pass | $0.74 |
| CI, PR #7 | Run 5's code again, after a docs-only commit ([43125077119](https://github.com/adammazhar/claimsense-ai/actions/runs/43125077119)) | 95.5% | 100% | **fail: adversarial EV-018**, but the job went green (D-041) | $0.74 |
| [6a](live-run-6a.txt) | The general Coverage Check line restored (D-042); CI fixed to pipefail | 100% | 100% | pass | $0.74 |
| **[6b](live-gate-run.txt)** | The same code, a second run, as required before pushing | **100%** | **100%** | **pass** | **$0.73** |
| CI, PR #7 | Run 6b's code ([43129923917](https://github.com/adammazhar/claimsense-ai/actions/runs/43129923917)), under pipefail | 100% | 100% | pass | $0.73 |
| CI, `main` | The merge commit `d9df0ba` ([43130785463](https://github.com/adammazhar/claimsense-ai/actions/runs/43130785463)) | 100% | 100% | pass | $0.73 |

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
(D-032).

**EV-018 then failed in CI on run 5's code** (43125077119). It flips between runs even with input
identical to Milestone 3's, because the models run at temperature 0 with no seed: the Responses API has
none (D-041). That's why D-042 restores the general Coverage Check line. Runs 6a and 6b, the two clean
local runs required before pushing, both passed with it. No held-out case's content informed any fix.

## Every CI live gate, read back from its log (D-041)

Until D-041, the `live-eval-gate` job couldn't fail on a failed gate. Its step piped `run_evals.py`
through `tee` under `bash -e` with no pipefail, so the job reported `tee`'s exit status. These are the
results each run actually printed:

| CI run | Date (UTC) | Branch, event | Commit | Job | Printed | Accuracy | Held-out | Fallbacks | Cost |
|---|---|---|---|---|---|---:|---:|---:|---:|
| [42405228638](https://github.com/adammazhar/claimsense-ai/actions/runs/42405228638) | 2026-11-07 19:14 | m3-ghcr-fix, PR | 090e838 | skipped (docs-only) | | | | | |
| [42405384290](https://github.com/adammazhar/claimsense-ai/actions/runs/42405384290) | 2026-11-07 19:16 | m3-ghcr-fix, dispatch | 090e838 | success | GATE: PASSED | 100% of 22 | 100% of 6 | 0 | $0.74 |
| [42406249709](https://github.com/adammazhar/claimsense-ai/actions/runs/42406249709) | 2026-11-07 19:26 | main, push | 365b28f | success | GATE: PASSED | 100% of 22 | 100% of 6 | 0 | $0.74 |
| [42406993462](https://github.com/adammazhar/claimsense-ai/actions/runs/42406993462) | 2026-11-07 19:35 | m3-evidence, PR | 30c8e2b | skipped (docs-only) | | | | | |
| [42407151574](https://github.com/adammazhar/claimsense-ai/actions/runs/42407151574) | 2026-11-07 19:37 | main, push | 4bdf889 | success | GATE: PASSED | 100% of 22 | 100% of 6 | 0 | $0.74 |
| [42409075537](https://github.com/adammazhar/claimsense-ai/actions/runs/42409075537) | 2026-11-07 20:02 | m3-ci-protection, PR | 836076b | success | GATE: PASSED | 100% of 22 | 100% of 6 | 0 | $0.74 |
| [42409592035](https://github.com/adammazhar/claimsense-ai/actions/runs/42409592035) | 2026-11-07 20:08 | main, push | 353f6fc | success | GATE: PASSED | 100% of 22 | 100% of 6 | 0 | $0.74 |
| [42410792293](https://github.com/adammazhar/claimsense-ai/actions/runs/42410792293) | 2026-11-07 20:23 | m3-evidence-pr5, PR | 9d95fc7 | skipped (docs-only) | | | | | |
| [42410945026](https://github.com/adammazhar/claimsense-ai/actions/runs/42410945026) | 2026-11-07 20:24 | main, push | c0668c5 | skipped (docs-only) | | | | | |
| [43123372074](https://github.com/adammazhar/claimsense-ai/actions/runs/43123372074) | 2026-11-11 23:54 | m4-integration, PR | 229b24f | success | GATE: PASSED | 100% of 22 | 100% of 6 | 0 | $0.74 |
| [43125077119](https://github.com/adammazhar/claimsense-ai/actions/runs/43125077119) | 2026-11-12 00:08 | m4-integration, PR | 6ad515f | **success (false)** | **GATE: FAILED** | 95.5% of 22 | 100% of 6 | 0 | $0.74 |
| [43129923917](https://github.com/adammazhar/claimsense-ai/actions/runs/43129923917) | 2026-11-12 00:47 | m4-integration, PR | 8eebe5e | success (pipefail) | GATE: PASSED | 100% of 22 | 100% of 6 | 0 | $0.73 |
| [43130785463](https://github.com/adammazhar/claimsense-ai/actions/runs/43130785463) | 2026-11-12 00:55 | main, push | d9df0ba | success (pipefail) | GATE: PASSED | 100% of 22 | 100% of 6 | 0 | $0.73 |

Every green job before 43125077119 printed `GATE: PASSED`, so the Milestone 3 results and PR #7's
first run are real. 43125077119 is the one false pass: EV-018 failed (D-042). The workflow now runs
every step with pipefail. Run locally on a case file whose mock gate fails, the step's exact shape
exits 0 under the old shell and 1 under the new one. `tests/test_ci_workflow.py` keeps it that way.

That run also corrects a claim made earlier: a docs-only commit on a pull request that changes code
does run the live gate, because D-030 compares the whole pull request with its base.

## The image

The `main` run pushed the image only after both gates passed, at the digest of the image the live gate
ran in (D-029):

```
ghcr.io/adammazhar/claimsense-ai@sha256:76b7fe65e1b9c44cf2e005c4e754f0224ed034be2a1ea59397c192c9c187986b
```

It is tagged `d9df0ba640422b5813e44311e7c6d14f6dcece1a` and `latest`. The pushed manifest's config is
the gated image's ID, so it is the same build that passed both gates.

## Cost

Every live run of Milestone 4, from the totals each run printed. There were no rate-limit or quota
errors.

| | Runs | Cost |
|---|---:|---:|
| Local live gate runs 1 to 5 | 5 | $3.43 |
| Control run (Milestone 3 code) | 1 | $0.71 |
| Live two-adjuster run | 1 | $0.03 |
| Local live gate runs 6a and 6b | 2 | $1.47 |
| CI live gates on PR #7 | 3 | $2.21 |
| CI live gate on `main` | 1 | $0.73 |
| **Total, 2026-11-11 and 12** | **13** | **$8.57** |
| A live gate run (run 6b) | | $0.73, $0.033 per claim |

The rows are rounded; the total is the sum of the unrounded figures.

This index was added in a docs-only pull request, so its live gate was skipped and its merge pushed no
image (D-030).

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
