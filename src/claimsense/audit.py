"""Audit records: every call, granted or denied, with user, action and resource (D-003).

Milestone 3 keeps them in memory and writes them to the log. Milestone 4 makes them durable.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger("claimsense.audit")


@dataclass
class AuditLog:
    records: list[dict] = field(default_factory=list)

    def record(self, user: str, action: str, resource: str, decision: str, **details) -> dict:
        entry = {"at": datetime.now(UTC).isoformat(), "user": user, "action": action, "resource": resource,
                 "decision": decision, **details}
        self.records.append(entry)
        logger.info(json.dumps(entry))
        return entry
