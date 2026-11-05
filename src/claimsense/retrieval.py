"""Deterministic clause retrieval: BM25 over the policy corpus, keyed by clause ID (D-005, D-019).

No embeddings and no network, so retrieval behaves the same in CI, on a laptop and in the container.
Every search in a run is recorded in a RetrievalLog; the citation validator trusts only that log.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .contracts import ClauseEntry, RetrievalHit, RetrievalQuery, RetrievalResult
from .guardrails import looks_like_injection

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be by for from has in is it of on or that the this to was were will with".split()
)
K1, B = 1.5, 0.75


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


class ClauseIndex:
    """BM25 index over one corpus. Results are ordered by score, then clause ID, so ties are stable."""

    def __init__(self, clauses: list[ClauseEntry]) -> None:
        self.clauses = {c.clause_id: c for c in clauses}
        self._terms = {
            c.clause_id: Counter(tokenize(" ".join([c.heading, c.section, c.text, *c.tags]))) for c in clauses
        }
        lengths = [sum(terms.values()) for terms in self._terms.values()]
        self._avg_length = sum(lengths) / len(lengths) if lengths else 0.0
        self._doc_freq: Counter[str] = Counter()
        for terms in self._terms.values():
            self._doc_freq.update(terms.keys())

    @classmethod
    def from_file(cls, path: Path) -> ClauseIndex:
        records = json.loads(path.read_text(encoding="utf-8"))
        return cls([ClauseEntry.model_validate(r) for r in records])

    def _score(self, clause_id: str, query_terms: list[str]) -> float:
        terms = self._terms[clause_id]
        length = sum(terms.values())
        score = 0.0
        for term in query_terms:
            freq = terms.get(term, 0)
            if not freq:
                continue
            n = self._doc_freq[term]
            idf = math.log(1 + (len(self._terms) - n + 0.5) / (n + 0.5))
            score += idf * freq * (K1 + 1) / (freq + K1 * (1 - B + B * length / self._avg_length))
        return score

    def search(self, query: RetrievalQuery) -> RetrievalResult:
        """Top-k clauses of one form with a positive score."""
        query_terms = tokenize(query.query)
        scored = [
            (self._score(cid, query_terms), cid)
            for cid, clause in self.clauses.items()
            if clause.form_number == query.form_number
        ]
        ranked = sorted((s for s in scored if s[0] > 0), key=lambda s: (-s[0], s[1]))[: query.top_k]
        hits = [
            RetrievalHit(clause_id=cid, score=round(score, 4), heading=self.clauses[cid].heading,
                         text=self.clauses[cid].text)
            for score, cid in ranked
        ]
        return RetrievalResult(query=query, hits=hits)


@dataclass
class RetrievalLog:
    """Every clause retrieved for one claim in one run. The citation validator's source of truth."""

    index: ClauseIndex
    form_number: str
    queries: list[str] = field(default_factory=list)
    hits: dict[str, RetrievalHit] = field(default_factory=dict)
    quarantined: list[str] = field(default_factory=list)

    def search(self, query: str, top_k: int) -> list[RetrievalHit]:
        """Search, quarantining any clause whose text carries instructions before a model can see it."""
        result = self.index.search(RetrievalQuery(query=query[:2000], form_number=self.form_number, top_k=top_k))
        self.queries.append(query)
        clean = []
        for hit in result.hits:
            if looks_like_injection(hit.text):
                if hit.clause_id not in self.quarantined:
                    self.quarantined.append(hit.clause_id)
                continue
            self.hits.setdefault(hit.clause_id, hit)
            clean.append(hit)
        return clean

    @property
    def retrieved_ids(self) -> list[str]:
        return list(self.hits)
