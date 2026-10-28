"""Policy administration system (PAS) contracts.

Read:   GET /policies/{policy_id}?as_of={loss_date}   -> Policy

The PAS returns the policy as it stood on the as_of date. Whether the policy responds is computed
in code from the term dates and the transaction history; status_field is shown to the adjuster
but never drives an outcome (D-004).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from .common import Contract, Money, PartyId, PolicyId, SyntheticName


class GetPolicyRequest(Contract):
    """Path and query parameters for GET /policies/{policy_id}?as_of={loss_date}."""

    policy_id: PolicyId
    as_of: date


class CoverageType(StrEnum):
    LIABILITY = "liability"
    COLLISION = "collision"
    COMPREHENSIVE = "comprehensive"
    MEDICAL_PAYMENTS = "medical_payments"


class Coverage(Contract):
    deductible: Money | None = None
    limit: Money | None = None


class TransactionType(StrEnum):
    ISSUED = "issued"
    MISSED_PAYMENT_NOTICE = "missed_payment_notice"
    PAYMENT_RECEIVED = "payment_received"
    CANCELED = "canceled"
    REINSTATED = "reinstated"
    RENEWED = "renewed"


class PolicyTransaction(Contract):
    on: date
    type: TransactionType
    note: str | None = None


class EndorsementType(StrEnum):
    EXCLUDED_DRIVER = "excluded_driver"


class Endorsement(Contract):
    type: EndorsementType
    form_number: str = Field(pattern=r"^SYN-")
    excluded_driver_name: SyntheticName | None = None

    @model_validator(mode="after")
    def _driver_named(self) -> Endorsement:
        if self.type is EndorsementType.EXCLUDED_DRIVER and self.excluded_driver_name is None:
            raise ValueError("an excluded-driver endorsement must name the driver")
        return self


class StatusField(StrEnum):
    """The PAS's cached status. Display only (D-004): the client's lapsed-policy bug lived here."""

    ACTIVE = "Active"
    LAPSED = "Lapsed"
    CANCELED = "Canceled"


class Policy(Contract):
    """Response body of GET /policies/{policy_id}?as_of={loss_date}."""

    policy_id: PolicyId
    as_of: date
    form_number: str = Field(pattern=r"^SYN-", description="Selects the clause wording in the corpus.")
    named_insured: PartyId
    named_insured_name: SyntheticName
    effective_date: date
    expiration_date: date
    status_field: StatusField
    transactions: list[PolicyTransaction] = Field(default_factory=list)
    coverages: dict[CoverageType, Coverage]
    endorsements: list[Endorsement] = Field(default_factory=list)
    vehicle_acv: Money = Field(description="Actual cash value of the insured vehicle, USD.")

    @model_validator(mode="after")
    def _term_order(self) -> Policy:
        if self.expiration_date <= self.effective_date:
            raise ValueError("expiration_date must be after effective_date")
        return self
