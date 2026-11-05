"""The co-pilot API. Identity here is a placeholder: X-User-Id is asserted, not authenticated.

Milestone 3 enforces entitlement in code before any agent runs, which is the part that must not move.
Milestone 4 replaces the header with a verified token. Do not expose this service before then (D-023).
"""

from __future__ import annotations

import logging
import os
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .clients import ClientSystemError, ClientSystems, ConflictError
from .contracts import ErrorCode, ErrorResponse, RecommendationResponse, RecommendRequest
from .mock_brain import brain_from_name
from .pipeline import ACTION, Pipeline, Refused
from .retrieval import ClauseIndex
from .settings import DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


def _error(status: int, code: ErrorCode, message: str, retryable: bool = False) -> JSONResponse:
    body = ErrorResponse(code=code, message=message, request_id=f"req-{uuid4().hex[:12]}", retryable=retryable)
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def create_app(pipeline: Pipeline | None = None) -> FastAPI:
    """Build the API. With no pipeline given, it wires one from the environment."""
    if pipeline is None:
        pipeline = Pipeline(clients=ClientSystems.from_env(), index=ClauseIndex.from_file(DATA_DIR / "clauses.json"),
                            brain=brain_from_name(os.environ.get("BRAIN", "mock")))
    app = FastAPI(title="ClaimSense co-pilot", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.pipeline = pipeline
    completed: dict[tuple[str, UUID], RecommendationResponse] = {}

    @app.exception_handler(RequestValidationError)
    async def _validation_failed(_, exc: RequestValidationError) -> JSONResponse:
        return _error(422, ErrorCode.VALIDATION_FAILED, f"request failed validation ({len(exc.errors())} errors)")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "brain": pipeline.brain.name}

    @app.post("/v1/claims/{claim_id}/recommendation")
    async def recommend(claim_id: str, body: RecommendRequest | None = None,
                        x_user_id: str | None = Header(default=None)):
        request = body or RecommendRequest()
        if not x_user_id:
            return _error(401, ErrorCode.UNAUTHENTICATED, "X-User-Id header is required")
        try:
            key = (claim_id, request.run_id) if request.run_id else None
            if key and key in completed:
                # A cached result never skips entitlement.
                await pipeline.authorize(x_user_id, claim_id)
                pipeline.audit.record(x_user_id, ACTION, claim_id, "granted", run_id=str(request.run_id), replay=True)
                return completed[key].model_dump(mode="json")
            response = await pipeline.recommend(x_user_id, claim_id, note=request.note, run_id=request.run_id)
        except Refused:
            # The same answer whether or not the claim exists (EV-019).
            return _error(403, ErrorCode.FORBIDDEN, "not entitled to this claim")
        except ConflictError:
            pipeline.audit.record(x_user_id, ACTION, claim_id, "error", reason="idempotency_conflict")
            return _error(409, ErrorCode.IDEMPOTENCY_CONFLICT, "this run_id was already used with a different result")
        except (ClientSystemError, ValidationError, httpx.HTTPError):
            pipeline.audit.record(x_user_id, ACTION, claim_id, "error", reason="client_system_unavailable")
            return _error(503, ErrorCode.UPSTREAM_UNAVAILABLE, "a client system is unavailable; no decision was made",
                          retryable=True)
        if key:
            completed[key] = response
        return response.model_dump(mode="json")

    return app
