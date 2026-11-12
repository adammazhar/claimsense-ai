"""The governed MCP door between the co-pilot and the client systems (Milestone 4, D-031 to D-037)."""

from .audit import AuditTrail, verify, verify_file
from .identity import Identity, RegistryMissing, SeatStore, SeatVerifier, hash_token, issue
from .ratelimit import RateLimiter
from .scope import SCOPES, Decision, authorize, redact
from .server import MODEL_TOOLS, TOOLS, Door, create_app

__all__ = ["AuditTrail", "Decision", "Door", "Identity", "MODEL_TOOLS", "RateLimiter", "RegistryMissing", "SCOPES",
           "SeatStore", "SeatVerifier", "TOOLS", "authorize", "create_app", "hash_token", "issue", "redact",
           "verify", "verify_file"]
