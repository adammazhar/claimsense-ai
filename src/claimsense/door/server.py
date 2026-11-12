"""The governed MCP door: the one way the co-pilot reaches a client system (D-031).

It bridges four systems: the CMS (claims, assignment, and the one write), the PAS (the policy as of
the loss date), the document store, and the clause library. It is an MCP server on the official SDK
(v2 `MCPServer`, streamable HTTP, D-032).

Every call goes through the same path, in code:

    bearer token -> seat (transport, before any tool runs; 401 if unknown, revoked or expired)
    -> rate limit -> validate arguments -> read the claim's routing metadata -> scope gate
    -> serve, with the CMS's own row filter underneath -> one audit row -> result or structured error

The audit row is written before anything is returned, so a denial is on record before its error
leaves the door (D-036). No tool takes an identity argument: identity comes only from the token.

Tools:
    whoami()                                            the seat the token resolves to
    get_claim(claim_id)                                 the CMS record, fraud details stripped by role
    get_policy(claim_id)                                the policy as of the loss date (no policy_id to bypass)
    get_claim_documents(claim_id)                       the claim's documents
    search_clauses(claim_id, query)                     clause search on the claim's form; the only model tool
    submit_draft_recommendation(claim_id, idempotency_key, draft)
                                                        the one write; a replay returns the original
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import httpx
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent
from pydantic import Field
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from ..clients import (
    BadRequestError,
    ClientSystems,
    ConflictError,
    NotFoundError,
    RowFilteredError,
    UnavailableError,
)
from ..contracts import RETRYABLE, ClaimAssignment, DoorError, DoorErrorCode, DraftRecommendationRequest, RetrievalQuery
from ..guardrails import looks_like_injection
from ..retrieval import ClauseIndex
from ..settings import DATA_DIR, REPO_ROOT, RETRIEVAL_TOP_K
from .audit import AuditTrail
from .identity import Identity, SeatStore, SeatVerifier, identity_from
from .ratelimit import RateLimiter
from .scope import authorize, redact

CLAIM_ID = re.compile(r"^CLM-\d{4}-\d{4}$")
CORRELATION_HEADER = "x-correlation-id"
MCP_PATH = "/mcp"
TOOLS = ("whoami", "get_claim", "get_policy", "get_claim_documents", "search_clauses",
         "submit_draft_recommendation")
MODEL_TOOLS = ("search_clauses",)  # the only tool an agent is offered (D-031)

MESSAGES = {
    DoorErrorCode.UNAUTHENTICATED: "A valid seat token is required.",
    DoorErrorCode.FORBIDDEN_SCOPE: "This seat is not permitted to access this claim.",
    DoorErrorCode.NOT_FOUND: "No such claim.",
    DoorErrorCode.RATE_LIMITED: "Too many calls from this seat. Retry after retry_after seconds.",
    DoorErrorCode.UPSTREAM_UNAVAILABLE: "A system of record is unavailable. Nothing was changed.",
    DoorErrorCode.IDEMPOTENCY_CONFLICT: "This idempotency key was already used with a different draft.",
    DoorErrorCode.INVALID_ARGUMENT: "The request was malformed.",
}
HINTS = {DoorErrorCode.FORBIDDEN_SCOPE: "The denial was logged in the audit trail.",
         DoorErrorCode.UNAUTHENTICATED: "The attempt was logged in the audit trail."}

# Typed tool inputs. The pattern is published in the schema; the door checks it itself, so a bad value
# is refused with a structured, audited invalid_argument instead of failing before the gate.
ClaimArg = Annotated[str, Field(description="The claim_id of the claim file you are working on.", max_length=64,
                                json_schema_extra={"pattern": CLAIM_ID.pattern})]
QueryArg = Annotated[str, Field(description="Words describing the coverage, exclusion, endorsement or duty to "
                                            "look up.", max_length=2000)]
KeyArg = Annotated[str, Field(description="claim_id:run_id", max_length=128)]


class _Refuse(Exception):
    def __init__(self, code: DoorErrorCode, reason: str, message: str | None = None,
                 retry_after: float | None = None) -> None:
        super().__init__(reason)
        self.code, self.reason, self.message, self.retry_after = code, reason, message, retry_after


def door_error(code: DoorErrorCode, request_id: str, correlation_id: str | None, message: str | None = None,
               retry_after: float | None = None) -> DoorError:
    return DoorError(code=code, message=message or MESSAGES[code], hint=HINTS.get(code),
                     retryable=code in RETRYABLE, retry_after=retry_after, correlation_id=correlation_id,
                     request_id=request_id)


def _text(payload: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=payload)])


@dataclass
class Door:
    """The door's state, shared by every MCP app built from it: seats, audit, limits, backends."""

    backends: ClientSystems
    index: ClauseIndex
    seats: SeatStore
    audit: AuditTrail = field(default_factory=AuditTrail)
    limiter: RateLimiter = field(default_factory=RateLimiter)
    allowed_hosts: list[str] = field(default_factory=lambda: ["door", "door:*", "localhost:*", "127.0.0.1:*"])
    retry_attempts: int = 3
    retry_base_seconds: float = 0.05
    _forms: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> Door:
        runtime = Path(os.environ.get("CLAIMSENSE_RUNTIME_DIR", REPO_ROOT / "runtime"))
        return cls(backends=ClientSystems.from_env(), index=ClauseIndex.from_file(DATA_DIR / "clauses.json"),
                   seats=SeatStore(path=Path(os.environ.get("SEAT_REGISTRY", runtime / "seats.json"))),
                   audit=AuditTrail(Path(os.environ.get("AUDIT_LOG", runtime / "audit.jsonl"))),
                   allowed_hosts=os.environ.get("DOOR_ALLOWED_HOSTS", "door:*,localhost:*,127.0.0.1:*").split(","))

    # ------------------------------------------------------------ the one path every call takes
    async def _call(self, ctx: Context | None, action: str, claim_id: str | None,
                    work: Callable[[Identity, ClaimAssignment | None], Awaitable[str]]) -> CallToolResult:
        identity = identity_from(get_access_token())
        request_id = f"req-{uuid4().hex[:12]}"
        correlation_id = ((ctx.headers if ctx else None) or {}).get(CORRELATION_HEADER)
        resource = f"claim/{claim_id}" if claim_id is not None else f"seat/{identity.user_id}"

        def audit(decision: str, reason: str | None) -> None:
            self.audit.record(request_id=request_id, correlation_id=correlation_id,
                              acting_identity=identity.user_id, role=identity.role, scope=identity.scope,
                              action=action, resource=resource if len(resource) <= 64 else "claim/<invalid>",
                              decision=decision, reason=reason)

        try:
            wait = self.limiter.take(identity.user_id)
            if wait is not None:
                raise _Refuse(DoorErrorCode.RATE_LIMITED, "rate_limited", retry_after=wait)
            assignment = None
            if claim_id is not None:
                if not CLAIM_ID.fullmatch(claim_id):
                    raise _Refuse(DoorErrorCode.INVALID_ARGUMENT, "bad_claim_id",
                                  "claim_id must look like CLM-YYYY-NNNN.")
                try:
                    assignment = await self._retry(lambda: self.backends.get_assignment(claim_id))
                except NotFoundError:
                    assignment = None
                decision = authorize(identity, assignment)
                if not decision.allowed:
                    raise _Refuse(decision.code, decision.reason)
                reason = decision.reason
            else:
                reason = "authenticated"
            payload = await work(identity, assignment)
        except _Refuse as refusal:
            audit("deny", refusal.reason)  # on record before the error leaves the door
            return self._error(refusal.code, request_id, correlation_id, refusal.message, refusal.retry_after)
        except RowFilteredError:
            audit("deny", "cms_row_filter")
            return self._error(DoorErrorCode.FORBIDDEN_SCOPE, request_id, correlation_id)
        except NotFoundError:
            audit("deny", "not_found_upstream")
            return self._error(DoorErrorCode.NOT_FOUND, request_id, correlation_id)
        except (UnavailableError, httpx.HTTPError) as exc:
            audit("deny", f"upstream_unavailable:{type(exc).__name__}")
            return self._error(DoorErrorCode.UPSTREAM_UNAVAILABLE, request_id, correlation_id)
        audit("allow", reason)
        return _text(payload)

    @staticmethod
    def _error(code: DoorErrorCode, request_id: str, correlation_id: str | None, message: str | None = None,
               retry_after: float | None = None) -> CallToolResult:
        body = door_error(code, request_id, correlation_id, message, retry_after)
        return CallToolResult(is_error=True, content=[TextContent(type="text", text=body.model_dump_json())])

    async def _retry(self, fetch: Callable[[], Awaitable[Any]]) -> Any:
        """Reads back off and retry on a transient failure. Writes reuse their idempotency key (D-037)."""
        for attempt in range(self.retry_attempts):
            try:
                return await fetch()
            except (UnavailableError, httpx.TransportError):
                if attempt == self.retry_attempts - 1:
                    raise
                await asyncio.sleep(self.retry_base_seconds * 2 ** attempt * (1 + random.random()))
        raise AssertionError("unreachable")

    # ------------------------------------------------------------ the work behind each tool
    @staticmethod
    def _acting(identity: Identity) -> tuple[str, str]:
        return identity.user_id, identity.role

    async def _claim(self, claim_id: str, identity: Identity):
        return await self._retry(lambda: self.backends.get_claim(claim_id, acting=self._acting(identity)))

    async def _form_number(self, claim_id: str, identity: Identity) -> str:
        if claim_id not in self._forms:
            claim = await self._claim(claim_id, identity)
            policy = await self._retry(lambda: self.backends.get_policy(
                claim.policy_id, claim.loss_datetime.date().isoformat()))
            self._forms[claim_id] = policy.form_number
        return self._forms[claim_id]

    def build(self) -> tuple[MCPServer, Starlette]:
        """A fresh MCP server and its ASGI app over this door's state (the SDK's session manager runs once)."""
        mcp = MCPServer(
            "claimsense-door",
            instructions="The governed door to ClaimSense's client systems. Identity comes from the bearer token.",
            token_verifier=SeatVerifier(self.seats),
            auth=AuthSettings(issuer_url="http://door", resource_server_url=f"http://door{MCP_PATH}",
                              required_scopes=[], validate_token_resource=False),
        )
        door = self

        @mcp.tool(description="The seat your token resolves to: user, role and scope.")
        async def whoami(ctx: Context) -> CallToolResult:
            async def work(identity, _):
                return json.dumps({"user_id": identity.user_id, "role": identity.role, "scope": identity.scope})
            return await door._call(ctx, "whoami", None, work)

        @mcp.tool(description="The claim record from the claims system, as this seat may see it.")
        async def get_claim(claim_id: ClaimArg, ctx: Context) -> CallToolResult:
            async def work(identity, _):
                return json.dumps(redact((await door._claim(claim_id, identity)).model_dump(mode="json"), identity))
            return await door._call(ctx, "get_claim", claim_id, work)

        @mcp.tool(description="The claim's policy as of the loss date, from policy administration.")
        async def get_policy(claim_id: ClaimArg, ctx: Context) -> CallToolResult:
            async def work(identity, _):
                claim = await door._claim(claim_id, identity)
                policy = await door._retry(lambda: door.backends.get_policy(
                    claim.policy_id, claim.loss_datetime.date().isoformat()))
                return policy.model_dump_json()
            return await door._call(ctx, "get_policy", claim_id, work)

        @mcp.tool(description="The claim's documents, with their text, from the document store.")
        async def get_claim_documents(claim_id: ClaimArg, ctx: Context) -> CallToolResult:
            async def work(identity, _):
                documents = await door._retry(lambda: door.backends.get_documents(claim_id))
                return json.dumps([d.model_dump(mode="json") for d in documents])
            return await door._call(ctx, "get_claim_documents", claim_id, work)

        @mcp.tool(description="Search the policy wording for this claim's policy form. "
                              "Returns clause IDs, headings and text.")
        async def search_clauses(
            claim_id: ClaimArg,
            query: QueryArg,

            ctx: Context,
        ) -> CallToolResult:
            async def work(identity, _):
                if not query.strip():
                    raise _Refuse(DoorErrorCode.INVALID_ARGUMENT, "empty_query", "query must not be empty.")
                form = await door._form_number(claim_id, identity)
                result = door.index.search(RetrievalQuery(query=query[:2000], form_number=form,
                                                          top_k=RETRIEVAL_TOP_K))
                # Clause text that carries instructions never reaches a model (D-019).
                clean = [h for h in result.hits if not looks_like_injection(h.text)]
                return json.dumps([{"clause_id": h.clause_id, "heading": h.heading, "text": h.text} for h in clean])
            return await door._call(ctx, "search_clauses", claim_id, work)

        @mcp.tool(description="Write the draft recommendation back to the claims system. Idempotent: a replay "
                              "with the same key and draft returns the original.")
        async def submit_draft_recommendation(
            claim_id: ClaimArg,
            idempotency_key: KeyArg,

            draft: DraftRecommendationRequest,
            ctx: Context,
        ) -> CallToolResult:
            async def work(identity, _):
                if draft.claim_id != claim_id:
                    raise _Refuse(DoorErrorCode.INVALID_ARGUMENT, "claim_mismatch", "draft.claim_id must match.")
                if draft.requested_by != identity.user_id:
                    raise _Refuse(DoorErrorCode.INVALID_ARGUMENT, "requested_by_not_acting_seat",
                                  "draft.requested_by must be the acting seat.")
                try:
                    written, replay = await door._retry(lambda: door.backends.post_draft(
                        draft, key=idempotency_key, acting=door._acting(identity)))
                except ConflictError as exc:
                    raise _Refuse(DoorErrorCode.IDEMPOTENCY_CONFLICT, "idempotency_conflict") from exc
                except BadRequestError as exc:
                    raise _Refuse(DoorErrorCode.INVALID_ARGUMENT, "bad_idempotency_key",
                                  "idempotency_key must be claim_id:run_id.") from exc
                return json.dumps({"recommendation": written.model_dump(mode="json"), "idempotent_replay": replay})
            return await door._call(ctx, "submit_draft_recommendation", claim_id, work)

        app = mcp.streamable_http_app(
            streamable_http_path=MCP_PATH, json_response=True, stateless_http=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                                         allowed_hosts=self.allowed_hosts, allowed_origins=[]))
        return mcp, _AuditUnauthenticated(app, self.audit)


class _AuditUnauthenticated:
    """ASGI wrapper: a request the transport refuses (401) never reaches a tool, so audit it here,
    before the 401 is sent."""

    def __init__(self, app, audit: AuditTrail) -> None:
        self.app, self.audit = app, audit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}

        async def audited_send(message):
            if message["type"] == "http.response.start" and message["status"] == 401:
                self.audit.record(request_id=f"req-{uuid4().hex[:12]}", correlation_id=headers.get(CORRELATION_HEADER),
                                  acting_identity="anonymous", role=None, scope=None, action="authenticate",
                                  resource="door", decision="deny",
                                  reason="missing_token" if "authorization" not in headers else "invalid_token")
            await send(message)

        return await self.app(scope, receive, audited_send)


def create_app(door: Door | None = None) -> Starlette:
    """The door as a long-running service (uvicorn --factory). Fails closed without a seat registry."""
    door = door or Door.from_env()
    mcp, mcp_app = door.build()

    async def health(_request):
        return JSONResponse({"status": "ok", "service": "mcp-door", "tools": list(TOOLS)})

    @asynccontextmanager
    async def lifespan(_app):
        async with mcp.session_manager.run():
            yield

    return Starlette(routes=[Route("/health", health), Mount("/", app=mcp_app)], lifespan=lifespan)
