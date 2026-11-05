"""One typed adapter per client system (R1): remapping the official fixtures changes only this seam.

Every response is validated against its contract, so a changed payload fails here, loudly, instead
of reaching the pipeline. Failures fail closed: no decision is ever made on partial data.
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


class ClientSystemError(Exception):
    """A client system failed or returned something outside its contract."""


class NotFoundError(ClientSystemError):
    pass


class ConflictError(ClientSystemError):
    """The CMS already holds a different draft for this claim_id + run_id (D-009)."""


def _json(response: httpx.Response) -> dict:
    if response.status_code == 404:
        raise NotFoundError(str(response.request.url.path))
    if response.status_code == 409:
        raise ConflictError(str(response.request.url.path))
    if response.status_code >= 400:
        raise ClientSystemError(f"{response.request.url.path} returned {response.status_code}")
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

    async def get_claim(self, claim_id: str) -> Claim:
        return Claim.model_validate(_json(await self.cms.get(f"/claims/{claim_id}")))

    async def get_policy(self, policy_id: str, as_of: str) -> Policy:
        return Policy.model_validate(_json(await self.pas.get(f"/policies/{policy_id}", params={"as_of": as_of})))

    async def get_documents(self, claim_id: str) -> list[Document]:
        listing = DocumentList.model_validate(_json(await self.documents.get(f"/claims/{claim_id}/documents")))
        return [
            Document.model_validate(_json(await self.documents.get(f"/documents/{meta.doc_id}")))
            for meta in listing.documents
        ]

    async def post_draft(self, body: DraftRecommendationRequest) -> DraftRecommendationResponse:
        """The only write. Idempotent on claim_id + run_id (D-009)."""
        response = await self.cms.post(
            f"/claims/{body.claim_id}/recommendations",
            content=body.model_dump_json(),
            headers={HEADER: idempotency_key(body.claim_id, body.run_id), "Content-Type": "application/json"},
        )
        return DraftRecommendationResponse.model_validate(_json(response))
