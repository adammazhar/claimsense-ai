"""Deterministic facts: everything here is computed in code and never delegated to a model (D-001).

Policy term comes from the dates and the transaction history, never the status field (D-004). Money
stays in Decimal. The eval checker recomputes the same values independently, and a test keeps the
two in agreement.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal

from .contracts import Claim, CoverageType, DeterministicFacts, LossType, Policy
from .contracts.documents import DocumentMeta, DocumentType
from .contracts.pas import TransactionType
from .settings import TOTAL_LOSS_THRESHOLD

PERIOD_BOUNDARY = time(0, 1)  # CLS-PER-006: 12:01 a.m. local time on the effective and expiration dates
_THRESHOLD = Decimal(TOTAL_LOSS_THRESHOLD)


def in_force_at(policy: Policy, loss: datetime) -> bool:
    """True if the loss is inside the policy period and the policy wasn't canceled at that time."""
    start = datetime.combine(policy.effective_date, PERIOD_BOUNDARY)
    end = datetime.combine(policy.expiration_date, PERIOD_BOUNDARY)
    if not start <= loss < end:
        return False
    canceled = False
    for txn in sorted(policy.transactions, key=lambda t: t.on):
        if txn.on > loss.date():
            break
        if txn.type is TransactionType.CANCELED:
            canceled = True
        elif txn.type is TransactionType.REINSTATED:
            canceled = False
    return not canceled


def coverage_type_for(loss_type: LossType) -> CoverageType:
    """Map a loss type to the first-party coverage that responds to it."""
    return CoverageType.COLLISION if loss_type is LossType.COLLISION else CoverageType.COMPREHENSIVE


def total_loss_ratio(estimate: Decimal, acv: Decimal) -> Decimal:
    return estimate / acv if acv and estimate else Decimal(0)


def payable_amount(claim: Claim, policy: Policy) -> Decimal:
    """min(estimate, ACV) minus the deductible, never below zero. Applies only to an APPROVE."""
    coverage = policy.coverages[coverage_type_for(claim.loss_type)]
    payable = min(claim.repair_estimate, policy.vehicle_acv) - (coverage.deductible or Decimal(0))
    return max(payable, Decimal(0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def days_since_inception(loss: datetime, effective: date) -> int:
    return (loss.date() - effective).days


def compute_facts(claim: Claim, policy: Policy, documents: list[DocumentMeta]) -> DeterministicFacts:
    """The facts for one claim. `payable` is set later, once the final outcome is known."""
    ratio = total_loss_ratio(claim.repair_estimate, policy.vehicle_acv)
    photos = [d for d in documents if d.type is DocumentType.PHOTOS and d.captured_on is not None]
    return DeterministicFacts(
        in_term=in_force_at(policy, claim.loss_datetime),
        coverage_present=coverage_type_for(claim.loss_type) in policy.coverages,
        total_loss_ratio=float(ratio.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
        total_loss_candidate=ratio >= _THRESHOLD,
        days_since_inception=days_since_inception(claim.loss_datetime, policy.effective_date),
        photos_before_inception=any(d.captured_on < policy.effective_date for d in photos) if photos else None,
    )
