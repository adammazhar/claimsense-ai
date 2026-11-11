"""Identity at the door: a bearer token per seat, resolved server-side to {user, role, scope} (D-033).

This simulates OAuth2 on-behalf-of (RFC 8693): presenting the seat token is the token exchange, and
the door never accepts identity from a tool argument. Only SHA-256 hashes of tokens are stored, a
seat can be revoked or expire, and the registry file is re-read when it changes, so a revocation
takes effect on the next call without a restart.

Production form: an OIDC identity provider (Cognito, Entra, Okta) issues the adjuster's token, the
co-pilot exchanges it for a door-audience token scoped to that adjuster (RFC 8693 token exchange),
or AgentCore Identity holds the exchange. The door's TokenVerifier then validates a signed JWT
instead of looking up a hash.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mcp.server.auth.provider import AccessToken, TokenVerifier

from ..contracts import Role, Seat, SeatRegistry
from .scope import scope_of

TOKEN_PREFIX = "csk_"  # makes a leaked token easy to find in a secret scan
DEFAULT_TTL = timedelta(days=30)


class RegistryMissing(RuntimeError):
    """The door fails closed: without a seat registry it refuses to start."""


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


@dataclass(frozen=True)
class Identity:
    """Who is acting. Resolved from the token by the door, never supplied by a model."""

    user_id: str
    role: str
    scope: str | None  # None: the role has no scope at the door (deny by default)

    @property
    def known_role(self) -> Role | None:
        try:
            return Role(self.role)
        except ValueError:
            return None


ANONYMOUS = Identity(user_id="anonymous", role="none", scope=None)


def issue(roster: list[dict], ttl: timedelta = DEFAULT_TTL, now: datetime | None = None
          ) -> tuple[SeatRegistry, dict[str, str]]:
    """Issue a fresh token for every seat in the roster. Returns the hashed registry and the tokens.

    The tokens are returned once, to be handed to their seats. Only the registry is kept by the door.
    """
    now = now or datetime.now(UTC)
    tokens, seats = {}, []
    for entry in roster:
        token = new_token()
        tokens[entry["user_id"]] = token
        seats.append(Seat(user_id=entry["user_id"], role=entry["role"], token_sha256=hash_token(token),
                          issued_at=now, expires_at=now + ttl))
    return SeatRegistry(seats=seats), tokens


class SeatStore:
    """The seat registry, from a file (compose) or from memory (tests and evals)."""

    def __init__(self, registry: SeatRegistry | None = None, path: Path | None = None) -> None:
        self._path, self._mtime = path, None
        self._lock = threading.Lock()
        self._by_hash: dict[str, Seat] = {}
        if path is not None:
            if not path.exists():
                raise RegistryMissing(
                    f"Seat registry {path} not found; the door refuses to start without one. "
                    "Run: .\\.venv\\Scripts\\python.exe scripts\\issue_seat_tokens.py")
            self._reload()
        elif registry is not None:
            self._index(registry)
        else:
            raise RegistryMissing("no seat registry given; the door refuses to start without one")

    def _index(self, registry: SeatRegistry) -> None:
        self._by_hash = {s.token_sha256: s for s in registry.seats}

    def _reload(self) -> None:
        mtime = self._path.stat().st_mtime_ns
        if mtime != self._mtime:
            self._index(SeatRegistry.model_validate_json(self._path.read_text(encoding="utf-8")))
            self._mtime = mtime

    def resolve(self, token: str, now: datetime | None = None) -> Identity | None:
        """The identity a token maps to, or None if it is unknown, revoked or expired."""
        with self._lock:
            if self._path is not None:
                self._reload()
            seat = self._by_hash.get(hash_token(token))
        now = now or datetime.now(UTC)
        if seat is None or seat.revoked_at is not None or seat.expires_at <= now:
            return None
        return Identity(user_id=seat.user_id, role=seat.role, scope=scope_of(seat.role))

    def revoke(self, user_id: str, at: datetime | None = None) -> None:
        """In-memory revocation, for tests. The issue script revokes in the file."""
        with self._lock:
            for key, seat in self._by_hash.items():
                if seat.user_id == user_id:
                    self._by_hash[key] = seat.model_copy(update={"revoked_at": at or datetime.now(UTC)})


class SeatVerifier(TokenVerifier):
    """The MCP SDK's hook: the transport calls this on every request, before any tool runs."""

    def __init__(self, store: SeatStore) -> None:
        self.store = store

    async def verify_token(self, token: str) -> AccessToken | None:
        identity = self.store.resolve(token)
        if identity is None:
            return None
        return AccessToken(token=token, client_id=identity.user_id, subject=identity.user_id,
                           scopes=[identity.role], claims={"role": identity.role, "scope": identity.scope})


def identity_from(access: AccessToken | None) -> Identity:
    if access is None or not access.subject:
        return ANONYMOUS
    claims = access.claims or {}
    return Identity(user_id=access.subject, role=str(claims.get("role")), scope=claims.get("scope"))
