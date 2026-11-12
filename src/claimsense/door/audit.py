"""The door's audit trail: one row per call, granted or denied, append-only and hash-chained (D-036).

Each row carries acting_identity, role, scope, action, resource, decision, ts, a request_id and the
caller's correlation_id. A row is written and flushed to disk before the call returns, so a denial is
on record before its error leaves the door. The writer only appends: there is no update or delete.
Each row's hash covers the previous row's hash, so an edited or removed row breaks the chain, and
`verify` finds it.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from ..contracts import AuditRow

GENESIS = "0" * 64


def _digest(prev_hash: str, fields: dict) -> str:
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


class AuditTrail:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.rows: list[AuditRow] = []
        self._lock = threading.Lock()
        self._last = GENESIS
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
                if lines:
                    self._last = json.loads(lines[-1])["hash"]

    def record(self, *, request_id: str, correlation_id: str | None, acting_identity: str, role: str | None,
               scope: str | None, action: str, resource: str, decision: str, reason: str | None = None) -> AuditRow:
        with self._lock:
            fields = {"ts": datetime.now(UTC), "request_id": request_id,
                      "correlation_id": correlation_id, "acting_identity": acting_identity, "role": role,
                      "scope": scope, "action": action, "resource": resource, "decision": decision,
                      "reason": reason, "prev_hash": self._last}
            # Hash exactly what is written: the row as serialized, without its own hash.
            serialized = AuditRow.model_validate(fields | {"hash": GENESIS}).model_dump(mode="json", exclude={"hash"})
            row = AuditRow.model_validate(serialized | {"hash": _digest(self._last, serialized)})
            if self.path is not None:
                with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(row.model_dump_json() + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            self._last = row.hash
            self.rows.append(row)
            return row

    def for_correlation(self, correlation_id: str) -> list[AuditRow]:
        return [r for r in self.rows if r.correlation_id == correlation_id]


def verify(lines: list[str]) -> tuple[bool, int | None]:
    """Check the chain. Returns (ok, index of the first bad row)."""
    prev = GENESIS
    for i, line in enumerate(lines):
        row = json.loads(line)
        claimed = row.pop("hash", None)
        if row.get("prev_hash") != prev or _digest(prev, row) != claimed:
            return False, i
        prev = claimed
    return True, None


def verify_file(path: Path) -> tuple[bool, int | None]:
    return verify([ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()])
