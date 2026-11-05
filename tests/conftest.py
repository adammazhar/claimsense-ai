"""Shared helpers: the full stack in process, with no ports, key or network."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from claimsense.api import create_app
from claimsense.clients import ClientSystems
from claimsense.mock_brain import MockBrain
from claimsense.mock_services import create_cms_app, create_documents_app, create_pas_app
from claimsense.pipeline import Pipeline
from claimsense.retrieval import ClauseIndex
from claimsense.settings import DATA_DIR

# Claim -> assigned adjuster, from data/synthetic/assignments.json.
ADJ1, ADJ2, ADJ3 = "adj-001", "adj-002", "adj-003"
APPROVE_CLAIM, DENY_CLAIM, FLAG_CLAIM, ROUTE_CLAIM = "CLM-2026-0001", "CLM-2026-0006", "CLM-2026-0011", "CLM-2026-0015"
OWNER = {APPROVE_CLAIM: ADJ1, DENY_CLAIM: ADJ1, FLAG_CLAIM: ADJ1, ROUTE_CLAIM: ADJ2, "CLM-2026-0002": ADJ2,
         "CLM-2026-0014": ADJ1, "CLM-2026-0019": ADJ3}


class Stack:
    def __init__(self, brain=None, stage_timeout: float = 5.0, transports: dict | None = None) -> None:
        self.brain = brain or MockBrain()
        self.cms_app = create_cms_app()
        self.requests: list[str] = []
        transports = transports or {}

        def client(app, name):
            transport = transports.get(name) or httpx.ASGITransport(app=app)

            async def log_request(request: httpx.Request) -> None:
                self.requests.append(f"{name} {request.method} {request.url.path}")

            return httpx.AsyncClient(transport=transport, base_url=f"http://{name}",
                                     event_hooks={"request": [log_request]})

        self.clients = ClientSystems(cms=client(self.cms_app, "cms"), pas=client(create_pas_app(), "pas"),
                                     documents=client(create_documents_app(), "documents"))
        self.pipeline = Pipeline(clients=self.clients, index=ClauseIndex.from_file(DATA_DIR / "clauses.json"),
                                 brain=self.brain, stage_timeout=stage_timeout)
        self.api = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.pipeline)),
                                     base_url="http://copilot")

    async def recommend(self, claim_id: str, user: str | None = None, **body) -> httpx.Response:
        user = user if user is not None else OWNER[claim_id]
        return await self.api.post(f"/v1/claims/{claim_id}/recommendation", headers={"X-User-Id": user}, json=body)

    async def drafts(self, claim_id: str) -> list[dict]:
        return (await self.clients.cms.get(f"/claims/{claim_id}/recommendations")).json()


@pytest.fixture
def run():
    """Run a coroutine to completion from a sync test."""
    return asyncio.run


@pytest.fixture
def stack() -> Stack:
    return Stack()
