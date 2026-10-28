"""Shared building blocks for the client-system contracts.

Every contract model is strict: unknown fields are rejected and instances are immutable, so a
change in a client system's payload fails loudly at the boundary instead of leaking into the
pipeline. Money is a Decimal with two places, never a float (D-001, D-008).
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints

# Identifier formats. All synthetic; the patterns match evals/cases_v0.yaml.
ClaimId = Annotated[str, StringConstraints(pattern=r"^CLM-\d{4}-\d{4}$")]
PolicyId = Annotated[str, StringConstraints(pattern=r"^POL-\d{4}$")]
DocumentId = Annotated[str, StringConstraints(pattern=r"^DOC-\d{4}-\d+$")]
ClauseId = Annotated[str, StringConstraints(pattern=r"^CLS-[A-Z]{2,3}-\d{3}$")]
UserId = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}-\d{3}$")]
PartyId = Annotated[str, StringConstraints(pattern=r"^PTY-\d{4}$")]
# A 17-character VIN that can never collide with a real one: every synthetic VIN starts "SYN".
SyntheticVin = Annotated[str, StringConstraints(pattern=r"^SYN[A-Z0-9]{14}$")]
# Synthetic people are named "Synthetic <role> <number>", so a real name can't pass validation.
SyntheticName = Annotated[str, StringConstraints(pattern=r"^Synthetic [A-Za-z]+ \d{3,4}$")]

Money = Annotated[
    Decimal,
    Field(ge=0, max_digits=12, decimal_places=2),
    PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json"),
]
Score = Annotated[float, Field(ge=0.0, le=1.0)]


class Contract(BaseModel):
    """Base for every contract model: strict, immutable, no unknown fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ErrorCode(StrEnum):
    """Machine-readable error codes shared by all three client systems."""

    UNAUTHENTICATED = "UNAUTHENTICATED"  # 401: missing or invalid service credential
    FORBIDDEN = "FORBIDDEN"  # 403: credential valid but not allowed this operation
    NOT_FOUND = "NOT_FOUND"  # 404: the requested record does not exist
    VALIDATION_FAILED = "VALIDATION_FAILED"  # 422: request failed schema validation
    IDEMPOTENCY_KEY_MISSING = "IDEMPOTENCY_KEY_MISSING"  # 400: write without Idempotency-Key
    IDEMPOTENCY_KEY_MISMATCH = "IDEMPOTENCY_KEY_MISMATCH"  # 400: key is not claim_id:run_id
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"  # 409: same key, different body
    RATE_LIMITED = "RATE_LIMITED"  # 429: back off and retry
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"  # 503: system of record is down


class ErrorResponse(Contract):
    """The error body every client-system endpoint returns on a non-2xx status."""

    code: ErrorCode
    message: str = Field(min_length=1, max_length=500)
    request_id: str = Field(min_length=1, description="Correlates with the audit record.")
    retryable: bool = Field(description="True only for RATE_LIMITED and UPSTREAM_UNAVAILABLE.")
