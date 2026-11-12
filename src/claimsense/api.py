"""The co-pilot API. Every /v1 route needs a bearer token: the adjuster's seat token (D-033).

The API doesn't decide who the caller is or what they may see. It forwards the token to the MCP door
on the request's own connection (the simulated on-behalf-of exchange), and the door resolves it to a
seat and enforces scope in code before any agent runs (D-031, D-034). A door refusal comes back to the
caller as the door's structured error, unchanged:

    401 unauthenticated    403 forbidden_scope    404 not_found (supervisors only)
    409 idempotency_conflict    422 invalid_argument    429 rate_limited    503 upstream_unavailable
"""

from __future__ import annotations

import logging
import os
import re
from uuid import UUID, uuid4

from fastapi import FastAPI, Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .contracts import DoorError, DoorErrorCode, ErrorCode, ErrorResponse, RecommendationResponse, RecommendRequest
from .door_client import DoorCallError, HttpDoorConnector
from .mock_brain import brain_from_name
from .pipeline import ACTION, Pipeline

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpx2").setLevel(logging.WARNING)

HTTP_STATUS = {
    DoorErrorCode.UNAUTHENTICATED: 401,
    DoorErrorCode.FORBIDDEN_SCOPE: 403,
    DoorErrorCode.NOT_FOUND: 404,
    DoorErrorCode.IDEMPOTENCY_CONFLICT: 409,
    DoorErrorCode.INVALID_ARGUMENT: 422,
    DoorErrorCode.RATE_LIMITED: 429,
    DoorErrorCode.UPSTREAM_UNAVAILABLE: 503,
}
_CORRELATION = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _validation_error(message: str) -> JSONResponse:
    body = ErrorResponse(code=ErrorCode.VALIDATION_FAILED, message=message, request_id=f"req-{uuid4().hex[:12]}",
                         retryable=False)
    return JSONResponse(status_code=422, content=body.model_dump(mode="json"))


def door_error_response(error: DoorError) -> JSONResponse:
    headers = {"Retry-After": str(max(1, round(error.retry_after)))} if error.retry_after else {}
    if error.correlation_id:
        headers["X-Correlation-Id"] = error.correlation_id
    return JSONResponse(status_code=HTTP_STATUS[error.code], content={"error": error.model_dump(mode="json")},
                        headers=headers)


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def create_app(pipeline: Pipeline | None = None) -> FastAPI:
    """Build the API. With no pipeline given, it wires one from the environment."""
    if pipeline is None:
        pipeline = Pipeline(door=HttpDoorConnector.from_env(), brain=brain_from_name(os.environ.get("BRAIN", "mock")))
    app = FastAPI(title="ClaimSense co-pilot", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.pipeline = pipeline
    completed: dict[tuple[str, UUID], RecommendationResponse] = {}

    @app.exception_handler(RequestValidationError)
    async def _validation_failed(_, exc: RequestValidationError) -> JSONResponse:
        return _validation_error(f"request failed validation ({len(exc.errors())} errors)")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "brain": pipeline.brain.name}

    @app.post("/v1/claims/{claim_id}/recommendation")
    async def recommend(claim_id: str, body: RecommendRequest | None = None,
                        authorization: str | None = Header(default=None),
                        x_correlation_id: str | None = Header(default=None)):
        request = body or RecommendRequest()
        correlation_id = x_correlation_id if x_correlation_id and _CORRELATION.fullmatch(x_correlation_id) \
            else f"corr-{uuid4().hex[:16]}"
        token = _bearer(authorization)
        if token is None:
            pipeline.audit.record("anonymous", ACTION, claim_id, "denied", reason="missing_bearer_token",
                                  correlation_id=correlation_id)
            return door_error_response(DoorError(
                code=DoorErrorCode.UNAUTHENTICATED, message="A bearer token is required.", retryable=False,
                correlation_id=correlation_id, request_id=f"req-{uuid4().hex[:12]}"))
        try:
            key = (claim_id, request.run_id) if request.run_id else None
            if key and key in completed:
                # A cached result never skips the gate: the door re-checks this caller's scope.
                user_id = await pipeline.check_access(token, claim_id, correlation_id)
                pipeline.audit.record(user_id, ACTION, claim_id, "granted", run_id=str(request.run_id), replay=True,
                                      correlation_id=correlation_id)
                return _ok(completed[key], correlation_id)
            response = await pipeline.recommend(token, claim_id, note=request.note, run_id=request.run_id,
                                                correlation_id=correlation_id)
        except DoorCallError as refused:
            return door_error_response(refused.error)
        if key:
            completed[key] = response
        return _ok(response, correlation_id)

    return app


def _ok(response: RecommendationResponse, correlation_id: str) -> JSONResponse:
    return JSONResponse(content=response.model_dump(mode="json"), headers={"X-Correlation-Id": correlation_id})
