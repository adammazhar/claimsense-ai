"""The whole stack in one process, for tests and the eval harness: no ports, key or network.

The mock client systems, the MCP door (with seat tokens minted in memory for this run only), the
pipeline and the API, wired as compose wires them, except every hop is an ASGI transport. Calls still
cross the real MCP protocol, the door's token check, scope gate and audit, so the mock gate in CI runs
through the door exactly as the deployment does (D-031).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from .api import create_app
from .clients import ClientSystems
from .door import AuditTrail, Door, RateLimiter, SeatStore, issue
from .door_client import InProcessDoorConnector
from .mock_services import create_cms_app, create_documents_app, create_pas_app
from .pipeline import Pipeline
from .retrieval import ClauseIndex
from .settings import DATA_DIR


class InProcessStack:
    def __init__(self, brain, data_dir: Path = DATA_DIR, stage_timeout: float | None = None,
                 transports: dict | None = None, audit_path: Path | None = None,
                 limiter: RateLimiter | None = None) -> None:
        self.brain = brain
        self.requests: list[str] = []
        transports = transports or {}
        self.cms_app = create_cms_app(data_dir)

        def client(app, name):
            transport = transports.get(name) or httpx.ASGITransport(app=app)

            async def log_request(request: httpx.Request) -> None:
                self.requests.append(f"{name} {request.method} {request.url.path}")

            return httpx.AsyncClient(transport=transport, base_url=f"http://{name}", timeout=30,
                                     event_hooks={"request": [log_request]})

        self.backends = ClientSystems(cms=client(self.cms_app, "cms"), pas=client(create_pas_app(data_dir), "pas"),
                                      documents=client(create_documents_app(data_dir), "documents"))
        roster = json.loads((data_dir / "seats.json").read_text(encoding="utf-8"))
        registry, self.tokens = issue(roster)
        self.seats = SeatStore(registry)
        self.door = Door(backends=self.backends, index=ClauseIndex.from_file(data_dir / "clauses.json"),
                         # The harness replays a whole case file under one seat in seconds, which no
                         # adjuster does; the production default is tested on its own (test_door_errors).
                         seats=self.seats, audit=AuditTrail(audit_path),
                         limiter=limiter or RateLimiter(capacity=2000, refill_per_second=1000),
                         retry_base_seconds=0.001)
        self.connector = InProcessDoorConnector(self.door)
        kwargs = {"stage_timeout": stage_timeout} if stage_timeout is not None else {}
        self.pipeline = Pipeline(door=self.connector, brain=brain, **kwargs)
        self.api = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.pipeline)),
                                     base_url="http://copilot", timeout=300)

    @property
    def audit_rows(self) -> list[dict]:
        return [r.model_dump(mode="json") for r in self.door.audit.rows]

    def auth(self, user: str | None) -> dict[str, str]:
        """The Authorization header for a seat. A user with no seat gets a token the door won't know."""
        if user is None:
            return {}
        return {"Authorization": f"Bearer {self.tokens.get(user, 'csk_not-a-seat')}"}

    async def recommend(self, claim_id: str, user: str | None, correlation_id: str | None = None,
                        **body) -> httpx.Response:
        headers = self.auth(user) | ({"X-Correlation-Id": correlation_id} if correlation_id else {})
        return await self.api.post(f"/v1/claims/{claim_id}/recommendation", headers=headers, json=body)

    async def drafts(self, claim_id: str) -> list[dict]:
        return (await self.backends.cms.get(f"/claims/{claim_id}/recommendations")).json()
