"""The mock identity provider's admin tool: issue, or revoke, the seat tokens the MCP door accepts (D-033).

Issue (the default) gives every seat in the roster a fresh random bearer token:
- the hashed seat registry goes to runtime/seats.json, which the door loads; it holds only SHA-256
  hashes of the tokens, never a token;
- the plaintext tokens go to .env as SEAT_TOKEN_<USER> lines, for the two-adjuster test and for local
  calls. Only SEAT_TOKEN_* lines are added or updated; every other line, OPENAI_API_KEY included, is
  kept as it was. .env is backed up to tmp/ first.
Revoke marks one seat revoked in the registry and drops its SEAT_TOKEN_ line. The door re-reads the
registry when it changes, so a revocation takes effect on the next call.

Nothing here prints a token: only the user, role, hash prefix and expiry. Stdlib only, so it runs on a
bare CI runner. In CI, tokens are minted per run and thrown away with the runner (no stored secret).

Production form: an OIDC identity provider issues the adjuster's token and the co-pilot exchanges it
for a door-scoped one (RFC 8693), or AgentCore Identity does; see D-033.

Usage:
    .\\.venv\\Scripts\\python.exe scripts\\issue_seat_tokens.py
    .\\.venv\\Scripts\\python.exe scripts\\issue_seat_tokens.py --revoke adj-002
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROSTER = ROOT / "data" / "synthetic" / "seats.json"
REGISTRY = ROOT / "runtime" / "seats.json"
ENV = ROOT / ".env"
BACKUPS = ROOT / "tmp"
PREFIX = "SEAT_TOKEN_"
TOKEN_PREFIX = "csk_"  # claimsense seat key; matches claimsense.door.identity


def env_key(user_id: str) -> str:
    return PREFIX + re.sub(r"[^A-Z0-9]", "_", user_id.upper())


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temp, path)


def update_env(path: Path, tokens: dict[str, str], drop: set[str] = frozenset(), backups: Path = BACKUPS) -> Path | None:
    """Set SEAT_TOKEN_* lines for `tokens`, remove those for `drop`, and leave every other line as is.
    Returns the backup's path, if there was a file to back up."""
    backup = None
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    if path.exists():
        backups.mkdir(parents=True, exist_ok=True)
        backup = backups / f".env.bak-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
        shutil.copy2(path, backup)
    wanted = {env_key(u): t for u, t in tokens.items()}
    dropped = {env_key(u) for u in drop}
    out, done = [], set()
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in dropped:
            continue
        if key in wanted:
            out.append(f"{key}={wanted[key]}")
            done.add(key)
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in wanted.items() if k not in done]
    _write_atomic(path, "\n".join(out) + "\n")
    return backup


def issue(roster: list[dict], ttl_days: int, now: datetime | None = None) -> tuple[dict, dict[str, str]]:
    now = now or datetime.now(UTC)
    tokens, seats = {}, []
    for entry in roster:
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        tokens[entry["user_id"]] = token
        seats.append({"user_id": entry["user_id"], "role": entry["role"],
                      "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
                      "issued_at": _iso(now), "expires_at": _iso(now + timedelta(days=ttl_days)), "revoked_at": None})
    return {"version": 1, "seats": seats}, tokens


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roster", type=Path, default=ROSTER)
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--env", type=Path, default=ENV)
    parser.add_argument("--backups", type=Path, default=BACKUPS)
    parser.add_argument("--ttl-days", type=int, default=30)
    parser.add_argument("--revoke", metavar="USER_ID")
    parser.add_argument("--container-writable", action="store_true",
                        help="POSIX only: let the door's non-root user (uid 1000) write the audit trail (CI)")
    args = parser.parse_args(argv)

    if args.revoke:
        if not args.registry.exists():
            print(f"no registry at {args.registry}; nothing to revoke")
            return 1
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        hits = [s for s in registry["seats"] if s["user_id"] == args.revoke and not s["revoked_at"]]
        if not hits:
            print(f"no active seat for {args.revoke}")
            return 1
        for seat in hits:
            seat["revoked_at"] = _iso(datetime.now(UTC))
        _write_atomic(args.registry, json.dumps(registry, indent=2) + "\n")
        update_env(args.env, {}, drop={args.revoke}, backups=args.backups)
        print(f"revoked {args.revoke}; the door refuses its token from the next call")
        return 0

    roster = json.loads(args.roster.read_text(encoding="utf-8"))
    registry, tokens = issue(roster, args.ttl_days)
    _write_atomic(args.registry, json.dumps(registry, indent=2) + "\n")
    backup = update_env(args.env, tokens, backups=args.backups)
    if args.container_writable and os.name == "posix":
        os.chmod(args.registry.parent, 0o777)
        audit = args.registry.parent / "audit.jsonl"
        audit.touch()
        os.chmod(audit, 0o666)
    print(f"wrote {args.registry} ({len(registry['seats'])} seats, hashes only)")
    print(f"updated {args.env}: {len(tokens)} {PREFIX}* lines; other lines unchanged"
          + (f"; backup at {backup}" if backup else ""))
    for seat in registry["seats"]:
        print(f"  {seat['user_id']:8} {seat['role']:17} sha256 {seat['token_sha256'][:12]}...  "
              f"expires {seat['expires_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
