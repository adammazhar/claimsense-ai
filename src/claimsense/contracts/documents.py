"""Document store contracts.

Reads:  GET /claims/{claim_id}/documents   -> DocumentList (metadata only)
        GET /documents/{doc_id}            -> Document (metadata plus extracted text)

Document text is untrusted input: it may contain instructions aimed at the co-pilot (EV-002,
EV-008, EV-018). It is passed to the agents as quoted evidence, never as instructions.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import AwareDatetime, Field

from .common import ClaimId, Contract, DocumentId


class DocumentType(StrEnum):
    POLICE_REPORT = "police_report"
    REPAIR_ESTIMATE = "repair_estimate"
    PHOTOS = "photos"
    INSURED_STATEMENT = "insured_statement"
    WITNESS_STATEMENT = "witness_statement"
    PASSENGER_STATEMENT = "passenger_statement"
    MEDICAL_NOTE = "medical_note"
    GARAGE_INCIDENT_REPORT = "garage_incident_report"
    RECORDED_CALL_TRANSCRIPT = "recorded_call_transcript"
    BODY_SHOP_LETTER = "body_shop_letter"


class ListDocumentsRequest(Contract):
    claim_id: ClaimId


class GetDocumentRequest(Contract):
    doc_id: DocumentId


class DocumentMeta(Contract):
    doc_id: DocumentId
    claim_id: ClaimId
    type: DocumentType
    received_at: AwareDatetime
    captured_on: date | None = Field(
        default=None, description="Capture date from file metadata (photos). Compared with inception in code."
    )
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="Hash of the text; pins the evidence a citation points at.")


class DocumentList(Contract):
    """Response body of GET /claims/{claim_id}/documents."""

    claim_id: ClaimId
    documents: list[DocumentMeta]


class Document(Contract):
    """Response body of GET /documents/{doc_id}."""

    meta: DocumentMeta
    text: str = Field(min_length=1)
