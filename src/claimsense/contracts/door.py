"""Contracts of the governed MCP door (Milestone 4, D-031 to D-037).

The door is the only way the co-pilot reaches a client system. These models are what crosses it:
the structured error a tool returns, the audit row every call writes, and the seat record that maps a
hashed bearer token to an identity.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, Field

from .common import Contract, UserId


class Role(StrEnum):
    """Seat roles the door grants scope to. Any other role string gets nothing (deny by default)."""

    ADJUSTER_PD = "adjuster_pd"  # physical-damage claims assigned to the seat
    ADJUSTER_BI = "adjuster_bi"  # bodily-injury claims assigned to the seat
    SIU = "siu"  # claims with an open SIU referral, fraud details included
    SUPERVISOR = "supervisor"  # every claim, fraud details included


class DoorErrorCode(StrEnum):
    """Errors an agent or the API can reason about, never a stack trace (W16 p.7)."""

    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN_SCOPE = "forbidden_scope"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    INVALID_ARGUMENT = "invalid_argument"


RETRYABLE = frozenset({DoorErrorCode.RATE_LIMITED, DoorErrorCode.UPSTREAM_UNAVAILABLE})


class DoorError(Contract):
    """The body of a failed tool call, and of the API error it becomes."""

    code: DoorErrorCode
    message: str = Field(min_length=1, max_length=500)
    hint: str | None = None
    retryable: bool
    retry_after: float | None = Field(default=None, ge=0, description="Seconds; set on rate_limited.")
    correlation_id: str | None = None
    request_id: str = Field(min_length=1, description="Matches the audit row of the call that failed.")


class AuditRow(Contract):
    """One row per tool call, granted or denied. Append-only and hash-chained (D-036)."""

    ts: AwareDatetime
    request_id: str
    correlation_id: str | None
    acting_identity: str = Field(description="The seat the bearer token resolved to; 'anonymous' if none.")
    role: str | None
    scope: str | None
    action: str = Field(description="The tool name.")
    resource: str = Field(description="For example claim/CLM-2026-0011.")
    decision: Literal["allow", "deny"]
    reason: str | None = None
    prev_hash: str
    hash: str


class Seat(Contract):
    """A seat in the registry. Only the token's SHA-256 is stored, never the token (D-033)."""

    user_id: UserId
    role: str = Field(min_length=1)
    token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    revoked_at: AwareDatetime | None = None


class SeatRegistry(Contract):
    """The file the door loads at startup. Missing means the door refuses to start (fail closed)."""

    version: Literal[1] = 1
    seats: list[Seat]
