"""One typed adapter per client system (R1): remapping the official fixtures changes only this seam.

Every response is validated against its contract, so a changed payload fails here, loudly, instead
of reaching the pipeline. Failures fail closed: no decision is ever made on partial data.

Since Milestone 4 only the MCP door imports this module (D-031). The co-pilot reaches these systems
through the door, never directly; tests/test_no_direct_backend.py holds that line. The door passes the
acting seat to the CMS (ACTING_*), which filters rows by it: the data-layer check under the gate (D-035).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from .contracts import (
    Claim,
    ClaimAssignment,
    Document,
    DocumentList,
    DraftRecommendationRequest,
    DraftRecommendationResponse,
    Policy,
)
from .contracts.idempotency import HEADER, idempotency_key

TIMEOUT = httpx.Timeout(10.0)
ACTING_USER, ACTING_ROLE = "X-Acting-User", "X-Acting-Role"


def acting_headers(acting: tuple[str, str] | None) -> dict[str, str]:
    return {ACTING_USER: acting[0], ACTING_ROLE: acting[1]} if acting else {}


class ClientSystemError(Exception):
    """A client system failed or returned something outside its contract."""


class NotFoundError(ClientSystemError):
    pass


class ConflictError(ClientSystemError):
    """The CMS already holds a different draft for this claim_id + run_id (D-009)."""


class RowFilteredError(ClientSystemError):
    """The CMS's own row filter refused the acting seat (403): the data layer under the gate."""


class BadRequestError(ClientSystemError):
    """The system refused the request as malformed (400), for example a mismatched idempotency key."""


class UnavailableError(ClientSystemError):
    """5xx or 429: worth retrying with backoff."""


def _json(response: httpx.Response) -> dict:
    path = str(response.request.url.path)
    if response.status_code == 404:
        raise NotFoundError(path)
    if response.status_code == 409:
        raise ConflictError(path)
    if response.status_code == 403:
        raise RowFilteredError(path)
    if response.status_code == 400:
        raise BadRequestError(path)
    if response.status_code == 429 or response.status_code >= 500:
        raise UnavailableError(f"{path} returned {response.status_code}")
    if response.status_code >= 400:
        raise ClientSystemError(f"{path} returned {response.status_code}")
    return response.json()


@dataclass
class ClientSystems:
    cms: httpx.AsyncClient
    pas: httpx.AsyncClient
    documents: httpx.AsyncClient

    @classmethod
    def from_env(cls) -> ClientSystems:
        return cls(
            cms=httpx.AsyncClient(base_url=os.environ.get("CMS_URL", "http://localhost:8001"), timeout=TIMEOUT),
            pas=httpx.AsyncClient(base_url=os.environ.get("PAS_URL", "http://localhost:8002"), timeout=TIMEOUT),
            documents=httpx.AsyncClient(base_url=os.environ.get("DOCS_URL", "http://localhost:8003"), timeout=TIMEOUT),
        )

    async def get_assignment(self, claim_id: str) -> ClaimAssignment:
        return ClaimAssignment.model_validate(_json(await self.cms.get(f"/claims/{claim_id}/assignment")))

    async def get_claim(self, claim_id: str, acting: tuple[str, str] | None = None) -> Claim:
        response = await self.cms.get(f"/claims/{claim_id}", headers=acting_headers(acting))
        return Claim.model_validate(_json(response))

    async def get_policy(self, policy_id: str, as_of: str) -> Policy:
        return Policy.model_validate(_json(await self.pas.get(f"/policies/{policy_id}", params={"as_of": as_of})))

    async def get_documents(self, claim_id: str) -> list[Document]:
        listing = DocumentList.model_validate(_json(await self.documents.get(f"/claims/{claim_id}/documents")))
        return [
            Document.model_validate(_json(await self.documents.get(f"/documents/{meta.doc_id}")))
            for meta in listing.documents
        ]

    async def post_draft(self, body: DraftRecommendationRequest, key: str | None = None,
                         acting: tuple[str, str] | None = None) -> tuple[DraftRecommendationResponse, bool]:
        """The only write. Idempotent on claim_id + run_id (D-009). Returns (result, was_replay)."""
        response = await self.cms.post(
            f"/claims/{body.claim_id}/recommendations",
            content=body.model_dump_json(),
            headers={HEADER: key or idempotency_key(body.claim_id, body.run_id), "Content-Type": "application/json",
                     **acting_headers(acting)},
        )
        return DraftRecommendationResponse.model_validate(_json(response)), response.status_code == 200
