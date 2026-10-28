"""The idempotency rule for the one write: POST /claims/{claim_id}/recommendations (D-009).

1. The key is claim_id + run_id. The caller sends it as the Idempotency-Key header, formatted
   "{claim_id}:{run_id}". A missing header is 400 IDEMPOTENCY_KEY_MISSING; a header that doesn't
   match the body's claim_id and run_id is 400 IDEMPOTENCY_KEY_MISMATCH.
2. First request with a key: the draft is created, 201, and the response is stored with a
   fingerprint of the body.
3. Replay (same key, same body fingerprint): 200 with the original response, byte for byte. No
   second draft is created, so a retry after a timeout is always safe.
4. Same key, different body: 409 IDEMPOTENCY_CONFLICT and nothing is written. A changed
   recommendation needs a new run_id.

The fingerprint is SHA-256 over the canonical JSON of the body (sorted keys, no whitespace), so
field order in the request doesn't matter. Keys are kept for the life of the claim: a run_id is
never reused. IdempotencyStore below is the reference behavior the CMS adapter and its tests
must match; the deployed store is a conditional write (planned: DynamoDB, D-012).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable
from uuid import UUID, uuid4

from .cms import DraftRecommendationRequest, DraftRecommendationResponse, RecommendationStatus
from .common import ErrorCode, ErrorResponse

HEADER = "Idempotency-Key"


def idempotency_key(claim_id: str, run_id: UUID | str) -> str:
    """The Idempotency-Key header value for a claim and run."""
    return f"{claim_id}:{run_id}"


def body_fingerprint(body: DraftRecommendationRequest) -> str:
    """SHA-256 of the canonical JSON of a request body."""
    canonical = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WriteResult:
    status: int
    body: DraftRecommendationResponse | ErrorResponse


@dataclass
class _Stored:
    fingerprint: str
    response: DraftRecommendationResponse


class IdempotencyStore:
    """Reference implementation of the rule, in memory."""

    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock
        self._by_key: dict[str, _Stored] = {}

    def submit(self, path_claim_id: str, header_key: str | None, body: DraftRecommendationRequest,
               request_id: str = "req-local") -> WriteResult:
        """Apply the rule to one POST and return the HTTP status and body."""
        if not header_key:
            return _error(400, ErrorCode.IDEMPOTENCY_KEY_MISSING, f"{HEADER} header is required", request_id)
        expected = idempotency_key(body.claim_id, body.run_id)
        if header_key != expected or path_claim_id != body.claim_id:
            return _error(400, ErrorCode.IDEMPOTENCY_KEY_MISMATCH,
                          f"{HEADER} must be '{{claim_id}}:{{run_id}}' matching the path and body", request_id)

        fingerprint = body_fingerprint(body)
        stored = self._by_key.get(expected)
        if stored is None:
            response = DraftRecommendationResponse(
                recommendation_id=uuid4(), claim_id=body.claim_id, run_id=body.run_id,
                status=RecommendationStatus.DRAFT, created_at=self._clock(),
            )
            self._by_key[expected] = _Stored(fingerprint, response)
            return WriteResult(201, response)
        if stored.fingerprint == fingerprint:
            return WriteResult(200, stored.response)
        return _error(409, ErrorCode.IDEMPOTENCY_CONFLICT,
                      "this claim_id and run_id were already used with a different body", request_id)

    def __len__(self) -> int:
        return len(self._by_key)


def _error(status: int, code: ErrorCode, message: str, request_id: str) -> WriteResult:
    return WriteResult(status, ErrorResponse(code=code, message=message, request_id=request_id, retryable=False))
