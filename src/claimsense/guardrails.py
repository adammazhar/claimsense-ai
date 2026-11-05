"""Code guardrails around the models. They run the same way for the real models and the mock brain.

- Input: find instruction-like text in untrusted input. It stays visible as evidence and is flagged;
  it never becomes a command (D-015).
- Citations: keep only clause and document IDs that actually exist for this claim (D-005).
- Output: fail the run if model text mentions another claim (R4).
- Precedence: DENY > ROUTE > FLAG > APPROVE, applied in code to the model's own signals (D-002).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .contracts import CodeOverride, DeterministicFacts, InjectionFlag, Outcome
from .contracts.copilot import CoverageReading

_INJECTION = re.compile(
    r"ignore (all |any )?(prior|previous|earlier) (instructions|constraints)"
    r"|\bsystem\s*:"
    r"|\b(ai assistant|automated reviewer|language model)\b"
    r"|fraud review (has )?(been )?(completed|passed)"
    r"|approve (this|the|it|now)\b"
    r"|(list|show|give) (me )?every other claim"
    r"|mark (it|this) (as )?final|close it\b"
    r"|skip the \w+( \w+)? review",
    re.IGNORECASE,
)
_CLAIM_ID = re.compile(r"\bCLM-\d{4}-\d{4}\b")
PRECEDENCE = {Outcome.DENY: 3, Outcome.ROUTE: 2, Outcome.FLAG: 1, Outcome.APPROVE: 0}


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION.search(text))


def scan_untrusted(source: str, text: str | None) -> list[InjectionFlag]:
    """Flag the instruction-like part of one piece of untrusted text."""
    if not text:
        return []
    match = _INJECTION.search(text)
    if not match:
        return []
    start, end = max(match.start() - 40, 0), min(match.end() + 40, len(text))
    return [InjectionFlag(source=source, quote=text[start:end].strip())]


@dataclass(frozen=True)
class CitationCheck:
    kept: list[str]
    removed: list[str]
    uncited: bool


def validate_citations(cited: Iterable[str], retrieved: Iterable[str]) -> CitationCheck:
    """Remove every citation that wasn't retrieved for this claim.

    The output is marked uncited if anything was removed or nothing remains: a model that invented
    one clause ID isn't trusted on the others without an adjuster looking (D-019).
    """
    allowed = set(retrieved)
    kept: list[str] = []
    removed: list[str] = []
    for cid in cited:
        bucket = kept if cid in allowed else removed
        if cid not in bucket:
            bucket.append(cid)
    return CitationCheck(kept=kept, removed=removed, uncited=bool(removed) or not kept)


def foreign_claim_ids(texts: Iterable[str], claim_id: str) -> set[str]:
    """Claim IDs in model output other than the claim being worked."""
    found: set[str] = set()
    for text in texts:
        found |= set(_CLAIM_ID.findall(text))
    return found - {claim_id}


def required_outcome(
    facts: DeterministicFacts,
    coverage_reading: CoverageReading,
    fraud_indicated: bool,
    injury_exposure: bool,
    missing_documents: list[str],
) -> tuple[Outcome, str]:
    """The lowest outcome the facts and the model's own signals allow, and the rule that set it."""
    if not facts.in_term:
        return Outcome.DENY, "policy not in force at the loss (code)"
    if not facts.coverage_present:
        return Outcome.DENY, "coverage for this loss type not on the policy (code)"
    if coverage_reading is CoverageReading.DOES_NOT_RESPOND:
        return Outcome.DENY, "Coverage Check found the policy does not respond"
    if fraud_indicated:
        return Outcome.ROUTE, "Claim Assessment found fraud indicators"
    if facts.total_loss_candidate:
        return Outcome.FLAG, "total-loss ratio at or above the threshold (code)"
    if injury_exposure:
        return Outcome.FLAG, "Claim Assessment found injury exposure"
    if missing_documents:
        return Outcome.FLAG, "Claim Assessment found required documents missing"
    if coverage_reading is CoverageReading.CANNOT_DETERMINE:
        return Outcome.FLAG, "Coverage Check could not determine coverage"
    return Outcome.APPROVE, "no rule raises the outcome"


def apply_precedence(drafted: Outcome, required: Outcome, rule: str) -> tuple[Outcome, CodeOverride | None]:
    """Final outcome is the higher of what was drafted and what the rules require."""
    if PRECEDENCE[required] > PRECEDENCE[drafted]:
        return required, CodeOverride(from_outcome=drafted, to_outcome=required, rule=rule)
    return drafted, None


def block_uncited(
    outcome: Outcome, facts: DeterministicFacts, uncited: bool
) -> tuple[Outcome, CodeOverride | None]:
    """An uncited coverage conclusion can't stand: send it to a licensed adjuster instead.

    A DENY from the term or coverage check stands, because code computed it. ROUTE stands, because
    it rests on documents and refers the file to people anyway.
    """
    deterministic_deny = not facts.in_term or not facts.coverage_present
    if uncited and not deterministic_deny and outcome in (Outcome.APPROVE, Outcome.DENY):
        rule = "coverage conclusion has no valid citation; sent to a licensed adjuster"
        return Outcome.FLAG, CodeOverride(from_outcome=outcome, to_outcome=Outcome.FLAG, rule=rule)
    return outcome, None
