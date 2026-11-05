"""Mock client systems (CMS, PAS, document store), served from data/synthetic/ and the contracts.

They stand in for the client's real systems, so they enforce the contracts instead of trusting them:
every record is validated at load, and errors use the shared ErrorResponse shape. They carry no
authentication in Milestone 3: compose keeps them on an internal network with no published port.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..contracts import (
    Claim,
    ClaimAssignment,
    Document,
    DocumentList,
    DraftRecommendationRequest,
    ErrorCode,
    ErrorResponse,
    Policy,
)
from ..contracts.idempotency import IdempotencyStore
from ..settings import DATA_DIR


def _load(data_dir: Path, name: str) -> list[dict]:
    return json.loads((data_dir / f"{name}.json").read_text(encoding="utf-8"))


def _error(status: int, code: ErrorCode, message: str, retryable: bool = False) -> JSONResponse:
    body = ErrorResponse(code=code, message=message, request_id=f"req-{uuid4().hex[:12]}", retryable=retryable)
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def _not_found(what: str) -> JSONResponse:
    return _error(404, ErrorCode.NOT_FOUND, f"no such {what}")


def _base_app(title: str) -> FastAPI:
    app = FastAPI(title=title, docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def _validation_failed(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error(422, ErrorCode.VALIDATION_FAILED, f"request failed validation ({len(exc.errors())} errors)")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": title}

    return app


def create_cms_app(data_dir: Path = DATA_DIR) -> FastAPI:
    app = _base_app("mock-cms")
    claims = {r["claim_id"]: Claim.model_validate(r) for r in _load(data_dir, "claims")}
    assignments = {r["claim_id"]: ClaimAssignment.model_validate(r) for r in _load(data_dir, "assignments")}
    store = IdempotencyStore()
    drafts: dict[str, list[dict]] = {}
    app.state.drafts = drafts

    @app.get("/claims/{claim_id}")
    async def get_claim(claim_id: str):
        claim = claims.get(claim_id)
        return claim.model_dump(mode="json") if claim else _not_found("claim")

    @app.get("/claims/{claim_id}/assignment")
    async def get_assignment(claim_id: str):
        assignment = assignments.get(claim_id)
        return assignment.model_dump(mode="json") if assignment else _not_found("claim")

    @app.post("/claims/{claim_id}/recommendations")
    async def post_recommendation(
        claim_id: str, body: DraftRecommendationRequest, idempotency_key: str | None = Header(default=None)
    ):
        if claim_id not in claims:
            return _not_found("claim")
        result = store.submit(claim_id, idempotency_key, body)
        if result.status == 201:
            drafts.setdefault(claim_id, []).append(body.model_dump(mode="json"))
        return JSONResponse(status_code=result.status, content=result.body.model_dump(mode="json"))

    @app.get("/claims/{claim_id}/recommendations")
    async def list_recommendations(claim_id: str) -> list[dict]:
        """Mock-only: lets the evals and tests confirm what landed in the CMS."""
        return drafts.get(claim_id, [])

    return app


def create_pas_app(data_dir: Path = DATA_DIR) -> FastAPI:
    app = _base_app("mock-pas")
    policies = {r["policy_id"]: Policy.model_validate(r) for r in _load(data_dir, "policies")}

    @app.get("/policies/{policy_id}")
    async def get_policy(policy_id: str, as_of: str):
        policy = policies.get(policy_id)
        if policy is None:
            return _not_found("policy")
        record = policy.model_dump(mode="json")
        record["as_of"] = as_of
        record["transactions"] = [t for t in record["transactions"] if t["on"] <= as_of]
        return Policy.model_validate(record).model_dump(mode="json")

    return app


def create_documents_app(data_dir: Path = DATA_DIR) -> FastAPI:
    app = _base_app("mock-documents")
    documents = [Document.model_validate(r) for r in _load(data_dir, "documents")]
    by_id = {d.meta.doc_id: d for d in documents}
    known_claims = {r["claim_id"] for r in _load(data_dir, "claims")}

    @app.get("/claims/{claim_id}/documents")
    async def list_documents(claim_id: str):
        if claim_id not in known_claims:
            return _not_found("claim")
        metas = [d.meta for d in documents if d.meta.claim_id == claim_id]
        return DocumentList(claim_id=claim_id, documents=metas).model_dump(mode="json")

    @app.get("/documents/{doc_id}")
    async def get_document(doc_id: str):
        document = by_id.get(doc_id)
        return document.model_dump(mode="json") if document else _not_found("document")

    return app
