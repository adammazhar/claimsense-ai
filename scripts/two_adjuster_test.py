"""The two-adjuster test against the running compose stack (Milestone 4 acceptance, W16 p.14).

Sends the identical request, POST /v1/claims/<claim>/recommendation with the same body, to the
co-pilot API twice: once with the bodily-injury adjuster's seat token and once with the
physical-damage adjuster's. It never calls the MCP door or a backend directly: the answer, the
refusal and the audit rows all come from the full agent path, through the door.

It passes only if:
- the BI adjuster gets 200 with the co-pilot's real output for the claim: a model verdict, no
  fallback, and no fraud details or access metadata;
- the PD adjuster gets 403 with the door's structured forbidden_scope error;
- the door's audit trail holds the matching rows: get_claim on the same resource, allow for one seat and
  deny for the other; the denial is the first and only row for its correlation ID; and the trail's hash
  chain verifies.

It prints both requests (tokens redacted), both responses and the audit rows, and writes the same
token-free transcript with --out. The brain is whatever the stack runs; --brain says which you expect,
and a mismatch fails fast:
    docker compose up --build --wait                                    # mock (CI)
    $env:BRAIN='openai'; docker compose up --build --wait               # live, costs a few cents
Stdlib only.

Usage:
    .\\.venv\\Scripts\\python.exe scripts\\two_adjuster_test.py --brain mock --out tmp\\two-adjuster.txt
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from claimsense.settings import PRICE_PER_MILLION  # noqa: E402  (stdlib-only module)

FRAUD_AND_ACCESS_FIELDS = ("siu_referral", "siu_referred", "claim_line")


def env_key(user_id: str) -> str:
    return "SEAT_TOKEN_" + user_id.upper().replace("-", "_")


def token_for(user_id: str, env_path: Path) -> str:
    key = env_key(user_id)
    if os.environ.get(key):
        return os.environ[key]
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    raise SystemExit(f"no {key} in the environment or {env_path}; run scripts/issue_seat_tokens.py first")


def call(method: str, url: str, headers: dict | None = None, body: dict | None = None) -> tuple[int, dict, str]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            raw = response.read().decode("utf-8")
            return response.status, dict(response.headers), raw
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read().decode("utf-8")


def _digest(prev: str, fields: dict) -> str:
    """The door's chain hash (claimsense.door.audit), recomputed independently."""
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev + canonical).encode("utf-8")).hexdigest()


def verify_chain(lines: list[str]) -> bool:
    prev = "0" * 64
    for line in lines:
        row = json.loads(line)
        claimed = row.pop("hash")
        if row["prev_hash"] != prev or _digest(prev, row) != claimed:
            return False
        prev = claimed
    return True


def read_audit(path: Path, correlation_ids: set[str], wait_seconds: float = 10.0) -> tuple[list[dict], list[str]]:
    deadline = time.time() + wait_seconds
    while True:
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()] if path.exists() else []
        rows = [json.loads(ln) for ln in lines]
        found = [r for r in rows if r.get("correlation_id") in correlation_ids]
        if {r["correlation_id"] for r in found} >= correlation_ids or time.time() > deadline:
            return found, lines
        time.sleep(0.5)


def cost(usage: list[dict]) -> float:
    total = 0.0
    for stage in usage:
        price = PRICE_PER_MILLION.get(stage["model"])
        if price:
            total += (stage["input_tokens"] * price["input"] + stage["output_tokens"] * price["output"]) / 1e6
    return round(total, 4)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--brain", choices=["mock", "openai"], default="mock", help="the brain you expect the stack to run")
    parser.add_argument("--claim", default="CLM-2026-0011")
    parser.add_argument("--allowed", default="adj-004", help="the seat whose scope covers the claim")
    parser.add_argument("--denied", default="adj-001", help="the seat whose scope does not")
    parser.add_argument("--audit", type=Path, default=ROOT / "runtime" / "audit.jsonl")
    parser.add_argument("--env", type=Path, default=ROOT / ".env")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    out: list[str] = []

    def say(text: str = "") -> None:
        print(text)
        out.append(text)

    problems: list[str] = []

    def check(ok: bool, what: str) -> None:
        say(f"  [{'ok' if ok else 'FAIL'}] {what}")
        if not ok:
            problems.append(what)

    status, _, raw = call("GET", f"{args.base_url}/health")
    running = json.loads(raw).get("brain") if status == 200 else None
    if running != args.brain:
        print(f"FAIL: the stack runs brain {running!r}, expected {args.brain!r} (status {status}).")
        return 1

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = f"/v1/claims/{args.claim}/recommendation"
    body: dict = {}
    seats = {"allowed": args.allowed, "denied": args.denied}
    say(f"# Two-adjuster test, {stamp}")
    say(f"stack: {args.base_url} (brain: {running}); claim: {args.claim}; all data synthetic")
    say()
    responses = {}
    for label, seat in seats.items():
        correlation_id = f"two-adjuster-{stamp}-{label}"
        headers = {"Authorization": f"Bearer {token_for(seat, args.env)}", "Content-Type": "application/json",
                   "X-Correlation-Id": correlation_id}
        say(f"## Request as {seat} ({label})")
        say(f"POST {path}")
        say(f"Authorization: Bearer <{seat} seat token, redacted>")
        say(f"X-Correlation-Id: {correlation_id}")
        say(f"body: {json.dumps(body)}")
        started = time.perf_counter()
        status, _, raw = call("POST", f"{args.base_url}{path}", headers, body)
        seconds = round(time.perf_counter() - started, 2)
        responses[label] = (status, raw, correlation_id)
        say(f"-> HTTP {status} in {seconds}s")
        say(json.dumps(json.loads(raw), indent=2))
        say()

    allowed_status, allowed_raw, allowed_cid = responses["allowed"]
    denied_status, denied_raw, denied_cid = responses["denied"]
    answer, refusal = json.loads(allowed_raw), json.loads(denied_raw)
    rows, lines = read_audit(args.audit, {allowed_cid, denied_cid})

    say("## Audit rows (the MCP door's trail, for these two requests)")
    for row in rows:
        say(json.dumps(row))
    say()
    say("## Checks")
    check(allowed_status == 200, f"{args.allowed} gets 200")
    check(answer.get("claim_id") == args.claim, "the answer is for the claim asked about")
    check(answer.get("verdict_source") == "model" and answer.get("fallback_reason") is None,
          "the answer is the co-pilot's model verdict, not a fallback")
    check(answer.get("status") == "draft", "the answer is a draft for the adjuster to confirm")
    check(not any(f'"{f}"' in allowed_raw for f in FRAUD_AND_ACCESS_FIELDS),
          "the answer carries no fraud details or access metadata (filtered)")
    check(denied_status == 403, f"{args.denied} gets 403")
    error = refusal.get("error", {})
    check(error.get("code") == "forbidden_scope" and error.get("retryable") is False,
          "the refusal is the door's structured forbidden_scope error")
    check(args.claim not in json.dumps({k: v for k, v in error.items()}) and "narrative" not in denied_raw,
          "the refusal carries no claim data")

    allowed_rows = [r for r in rows if r["correlation_id"] == allowed_cid]
    denied_rows = [r for r in rows if r["correlation_id"] == denied_cid]
    gate_allow = next((r for r in allowed_rows if r["action"] == "get_claim"), None)
    check(gate_allow is not None and (gate_allow["acting_identity"], gate_allow["decision"], gate_allow["resource"])
          == (args.allowed, "allow", f"claim/{args.claim}"), f"audit: get_claim allow for {args.allowed}")
    check(len(denied_rows) == 1, "audit: the denial is the first and only row for its request")
    deny = denied_rows[0] if denied_rows else {}
    check((deny.get("acting_identity"), deny.get("action"), deny.get("decision"), deny.get("resource"))
          == (args.denied, "get_claim", "deny", f"claim/{args.claim}"), f"audit: get_claim deny for {args.denied}")
    check(deny.get("request_id") == error.get("request_id"), "audit: the deny row's request_id is the error's")
    check(bool(lines) and verify_chain(lines), "audit: the hash chain over the whole trail verifies")
    check(all(r.get("scope") for r in (gate_allow or {}, deny)), "audit: both rows carry the seat's scope")

    if answer.get("usage"):
        say()
        say(f"model cost of the answered request: ${cost(answer['usage']):.4f} "
            f"({sum(u['input_tokens'] for u in answer['usage'])} input, "
            f"{sum(u['output_tokens'] for u in answer['usage'])} output tokens)")
    say()
    say("PASS" if not problems else f"FAIL ({len(problems)} checks)")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
