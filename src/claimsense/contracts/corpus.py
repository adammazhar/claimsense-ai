"""Policy clause corpus contracts.

The corpus is not a client system; it is the searchable set of policy form wordings, indexed at
clause level and keyed by clause ID (D-005). The coverage agent's only tool searches it, and the
citation validator keeps only clause IDs present in the RetrievalResult.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from .common import ClauseId, Contract


class ClauseEntry(Contract):
    """One clause of a policy form."""

    clause_id: ClauseId
    form_number: str = Field(pattern=r"^SYN-")
    form_edition: date
    section: str = Field(min_length=1, description="For example, 'Part D: Coverage for damage to your auto'.")
    heading: str = Field(min_length=1)
    text: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list, description="Coverage or topic tags used to filter retrieval.")
    supersedes: ClauseId | None = None


class RetrievalQuery(Contract):
    query: str = Field(min_length=1, max_length=2000)
    form_number: str = Field(pattern=r"^SYN-")
    top_k: int = Field(default=5, ge=1, le=20)


class RetrievalHit(Contract):
    clause_id: ClauseId
    score: float
    heading: str
    text: str


class RetrievalResult(Contract):
    """What retrieval returned. The citation validator checks citations against these IDs."""

    query: RetrievalQuery
    hits: list[RetrievalHit]

    @model_validator(mode="after")
    def _unique_hits(self) -> RetrievalResult:
        ids = [h.clause_id for h in self.hits]
        if len(ids) != len(set(ids)):
            raise ValueError("retrieval hits must not repeat a clause_id")
        return self

    def retrieved_ids(self) -> frozenset[str]:
        return frozenset(h.clause_id for h in self.hits)
