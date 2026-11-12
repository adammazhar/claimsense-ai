"""Shared helpers: the full stack in process, through the MCP door, with no ports, key or network."""

from __future__ import annotations

import asyncio

import pytest

from claimsense.inprocess import InProcessStack
from claimsense.mock_brain import MockBrain

# Claim -> assigned adjuster, from data/synthetic/assignments.json.
ADJ1, ADJ2, ADJ3, ADJ_BI = "adj-001", "adj-002", "adj-003", "adj-004"
SUPERVISOR, SIU, CUSTOMER_SERVICE = "sup-001", "siu-001", "cs-021"
APPROVE_CLAIM, DENY_CLAIM, FLAG_CLAIM, ROUTE_CLAIM = "CLM-2026-0001", "CLM-2026-0006", "CLM-2026-0011", "CLM-2026-0015"
SIU_CLAIM = "CLM-2026-0016"  # the one claim with an open SIU referral
OWNER = {APPROVE_CLAIM: ADJ1, DENY_CLAIM: ADJ1, FLAG_CLAIM: ADJ_BI, ROUTE_CLAIM: ADJ2, "CLM-2026-0002": ADJ2,
         "CLM-2026-0014": ADJ_BI, "CLM-2026-0019": ADJ3, SIU_CLAIM: ADJ3}


class Stack(InProcessStack):
    def __init__(self, brain=None, stage_timeout: float = 5.0, transports: dict | None = None, **kwargs) -> None:
        super().__init__(brain or MockBrain(), stage_timeout=stage_timeout, transports=transports, **kwargs)

    @property
    def clients(self):
        """The mock systems' own clients, for tests that inspect or poke a backend behind the door."""
        return self.backends

    async def recommend(self, claim_id: str, user: str | None = "", correlation_id: str | None = None, **body):
        user = OWNER[claim_id] if user == "" else user
        return await super().recommend(claim_id, user, correlation_id=correlation_id, **body)


@pytest.fixture
def run():
    """Run a coroutine to completion from a sync test."""
    return asyncio.run


@pytest.fixture
def stack() -> Stack:
    return Stack()
