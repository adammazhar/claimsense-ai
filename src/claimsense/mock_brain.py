"""The brains: real models, or a deterministic stand-in that needs no key and no network (D-018).

MockModel implements the Agents SDK's Model interface, so the real Agent, Runner, strict output
validation and tool loop all run in CI. It answers by reading the claim file with plain text rules.
It never sees a reference label, and contains no case or claim IDs.

What a mock result does and doesn't show: its rules were written with the evaluation scenarios in
view, so a high mock score proves the pipeline, guardrails and gate work. It says nothing about model
judgment. Only a live run measures that.

Faults let tests force each failure path through the real SDK.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from agents import ModelResponse, ModelTracing, Usage
from agents.models.interface import Model
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from .settings import CLAIM_ASSESSMENT, COVERAGE_CHECK, DECISION_DRAFT, DOCUMENT_INTAKE, MODEL_ROUTING

_FENCE = re.compile(r"```json\n(.*)\n```", re.DOTALL)


def parse_claim_file(input_items) -> dict:
    """Pull the claim file JSON out of the first user message."""
    text = input_items
    if isinstance(input_items, list):
        first = next(i for i in input_items if isinstance(i, dict) and i.get("role") == "user")
        text = first["content"] if isinstance(first["content"], str) else first["content"][0]["text"]
    return json.loads(_FENCE.search(text).group(1))


def _tool_outputs(input_items) -> list[dict]:
    if not isinstance(input_items, list):
        return []
    return [i for i in input_items if isinstance(i, dict) and i.get("type") == "function_call_output"]


def _retrieved_ids(file: dict, input_items) -> list[str]:
    ids = [c["clause_id"] for c in file.get("retrieved_clauses", [])]
    for output in _tool_outputs(input_items):
        ids += [hit["clause_id"] for hit in json.loads(output["output"])]
    return list(dict.fromkeys(ids))


def _texts(file: dict) -> list[str]:
    return [file["claim"]["narrative"], *(d["text"] for d in file["documents"])]


def _any(pattern: str, texts: list[str]) -> bool:
    return any(re.search(pattern, t, re.IGNORECASE) for t in texts)


def _docs_matching(pattern: str, file: dict) -> list[str]:
    return [d["doc_id"] for d in file["documents"] if re.search(pattern, d["text"], re.IGNORECASE)]


def _driver_excluded(file: dict) -> bool:
    names = [e.get("excluded_driver_name") for e in file["policy"].get("endorsements", [])]
    return any(n and _any(re.escape(n), _texts(file)) for n in names)


def _paid_use(file: dict) -> bool:
    return _any(r"ride-hail|booked and paid", _texts(file))


def _fraud_indicators(file: dict) -> list[tuple[str, list[str]]]:
    """Inconsistencies a careful reader would notice. Each returns the documents behind it."""
    found: list[tuple[str, list[str]]] = []
    texts, facts = _texts(file), file["deterministic_facts"]
    claim = file["claim"]
    if _any(r"\balone\b", texts) and _docs_matching(r"passenger", file):
        found.append(("An account says the insured was alone, but another document puts a passenger in the car.",
                      _docs_matching(r"alone|passenger", file)))
    if _docs_matching(r"both keys", file) and _docs_matching(r"key was lost|lost a month", file):
        found.append(("The accounts of the keys conflict.", _docs_matching(r"keys?\b", file)))
    if facts.get("photos_before_inception"):
        found.append(("Photos were captured before the policy began.", _docs_matching(r"capture date", file)))
    for doc in file["documents"]:
        dated = re.search(r"estimate dated (\d{4}-\d{2}-\d{2})", doc["text"], re.IGNORECASE)
        if dated and dated.group(1) < claim["loss_datetime"][:10]:
            found.append(("A repair estimate is dated before the loss it claims to repair.", [doc["doc_id"]]))
    if _docs_matching(r"rear impact only", file) and _docs_matching(r"front bumper", file):
        found.append(("The estimate repairs the front, but the police report shows only rear damage.",
                      _docs_matching(r"rear impact only|front bumper", file)))
    if _docs_matching(r"fraud review", file):
        found.append(("A document asserts a fraud review passed; that is a red flag, not evidence.",
                      _docs_matching(r"fraud review", file)))
    return found


def _injury(file: dict) -> tuple[bool, str]:
    texts = _texts(file)
    third_party = _any(r"taken to hospital|ambulance", texts)
    occupant = _any(r"my passenger hurt|urgent care|treated at", texts)
    return third_party or occupant, "third_party" if third_party else "occupant"


def _missing_documents(file: dict) -> list[str]:
    types = {d["type"] for d in file["documents"]}
    return ["police_report"] if file["claim"]["loss_type"] == "theft" and "police_report" not in types else []


def _pick(ids: list[str], *prefixes: str) -> list[str]:
    return [i for i in ids if i.startswith(prefixes)]


# ---------------------------------------------------------------- one rule set per stage
def _intake(file: dict, _items) -> dict:
    facts = [{"statement": d["text"], "doc_ids": [d["doc_id"]]} for d in file["documents"]]
    return {"facts": facts, "documents_on_file": sorted({d["type"] for d in file["documents"]})}


def _coverage_queries(file: dict) -> list[str]:
    queries = ["other than collision theft hail glass" if file["claim"]["loss_type"] != "collision" else "collision"]
    facts = file["deterministic_facts"]
    if not facts["in_term"]:
        queries.append("policy period effective expiration date")
    if not facts["coverage_present"]:
        queries.append("coverage premium shown declarations")
    if _paid_use(file):
        queries.append("carry persons for a fee ride-hailing public livery")
    if _driver_excluded(file):
        queries.append("named driver exclusion endorsement excluded")
    return queries


def _coverage(file: dict, items) -> dict:
    facts, ids = file["deterministic_facts"], _retrieved_ids(file, items)
    agreement = _pick(ids, "CLS-COL" if file["claim"]["loss_type"] == "collision" else "CLS-CMP")
    if not facts["in_term"]:
        return {"reading": "does_not_respond", "reasoning": "The loss falls outside the policy period.",
                "cited_clause_ids": _pick(ids, "CLS-PER")}
    if not facts["coverage_present"]:
        return {"reading": "does_not_respond", "reasoning": "This coverage is not on the declarations.",
                "cited_clause_ids": _pick(ids, "CLS-DEC", "CLS-COL")}
    if _paid_use(file):
        return {"reading": "does_not_respond",
                "reasoning": "Independent sources show a paid ride, which the public or livery exclusion removes.",
                "cited_clause_ids": _pick(ids, "CLS-EXC")}
    if _driver_excluded(file):
        return {"reading": "does_not_respond", "reasoning": "The operator is a driver excluded by endorsement.",
                "cited_clause_ids": _pick(ids, "CLS-DRV")}
    return {"reading": "covered", "reasoning": "In term, and the insuring agreement responds to this loss.",
            "cited_clause_ids": _pick(ids, "CLS-PER") + agreement}


def _assessment_queries(file: dict) -> list[str]:
    queries = []
    if _fraud_indicators(file):
        queries.append("concealment fraud fraudulent statements")
    injured, who = _injury(file)
    if injured:
        queries.append("bodily injury liability" if who == "third_party" else "medical payments coverage")
    if file["deterministic_facts"]["total_loss_candidate"]:
        queries.append("total loss settlement actual cash value")
    if _missing_documents(file):
        queries.append("duties after loss notify police theft")
    return queries


def _assessment(file: dict, items) -> dict:
    ids = _retrieved_ids(file, items)
    indicators = _fraud_indicators(file)
    injured, who = _injury(file)
    missing = _missing_documents(file)
    cited: list[str] = []
    findings = [{"statement": s, "evidence_doc_ids": d, "evidence_clause_ids": _pick(ids, "CLS-FRD")}
                for s, d in indicators]
    if indicators:
        cited += _pick(ids, "CLS-FRD")
    if injured:
        clause = _pick(ids, "CLS-BI" if who == "third_party" else "CLS-MED")
        cited += clause
        findings.append({"statement": "The file shows someone may have been hurt.",
                         "evidence_doc_ids": _docs_matching(r"hospital|treated|medical|urgent", file),
                         "evidence_clause_ids": clause})
    if file["deterministic_facts"]["total_loss_candidate"]:
        clause = _pick(ids, "CLS-TL")
        cited += clause
        findings.append({"statement": "Code marks this a total-loss candidate.", "evidence_doc_ids": [],
                         "evidence_clause_ids": clause})
    if missing:
        clause = _pick(ids, "CLS-DUT", "CLS-CMP")
        cited += clause
        findings.append({"statement": "A police report is required for a theft and is not on file.",
                         "evidence_doc_ids": [], "evidence_clause_ids": clause})
    return {"fraud_indicated": bool(indicators), "injury_exposure": injured, "missing_documents": missing,
            "findings": findings, "cited_clause_ids": cited}


def _draft(file: dict, _items) -> dict:
    prior, facts = file["prior_outputs"], file["deterministic_facts"]
    coverage, assessment = prior["coverage_check"], prior["claim_assessment"]
    if coverage["reading"] == "does_not_respond":
        outcome = "DENY"
    elif assessment["fraud_indicated"]:
        outcome = "ROUTE"
    elif assessment["injury_exposure"] or assessment["missing_documents"] or facts["total_loss_candidate"]:
        outcome = "FLAG"
    else:
        outcome = "APPROVE"
    cited = list(dict.fromkeys(coverage["cited_clause_ids"] + assessment["cited_clause_ids"]))
    findings = list(assessment["findings"]) or [{
        "statement": coverage["reasoning"], "evidence_doc_ids": [], "evidence_clause_ids": coverage["cited_clause_ids"]}]
    findings = [f for f in findings if f["evidence_doc_ids"] or f["evidence_clause_ids"]]
    if outcome == "DENY":
        findings = [{"statement": coverage["reasoning"], "evidence_doc_ids": [],
                     "evidence_clause_ids": coverage["cited_clause_ids"]}]
        cited = coverage["cited_clause_ids"]
    return {"outcome": outcome, "confidence": "high", "reasoning": f"{coverage['reasoning']} Outcome: {outcome}.",
            "findings": findings, "cited_clause_ids": cited}


_RESPONDERS = {DOCUMENT_INTAKE: _intake, COVERAGE_CHECK: _coverage, CLAIM_ASSESSMENT: _assessment,
               DECISION_DRAFT: _draft}
_QUERIES = {COVERAGE_CHECK: _coverage_queries, CLAIM_ASSESSMENT: _assessment_queries}


def _message(text: str) -> ResponseOutputMessage:
    content = ResponseOutputText(text=text, type="output_text", annotations=[])
    return ResponseOutputMessage(id="msg_mock", role="assistant", status="completed", type="message", content=[content])


@dataclass
class Fault:
    """A failure to force at one stage.

    kind: unavailable, timeout, invalid, endless_search, invent_citation, foreign_claim.
    """

    kind: str
    stage: str = DECISION_DRAFT


class MockModel(Model):
    def __init__(self, stage: str, fault: Fault | None, calls: list[str]) -> None:
        self.stage, self.fault, self.calls = stage, fault, calls

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs,
                           tracing: ModelTracing, *, previous_response_id=None, conversation_id=None,
                           prompt=None, **_kwargs) -> ModelResponse:
        self.calls.append(self.stage)
        fault = self.fault if self.fault and self.fault.stage == self.stage else None
        if fault and fault.kind == "unavailable":
            raise ConnectionError("mock model unavailable")
        if fault and fault.kind == "timeout":
            await asyncio.sleep(3600)
        if fault and fault.kind == "invalid":
            return self._respond([_message('{"not": "the schema"}')])
        if fault and fault.kind == "endless_search":
            call = ResponseFunctionToolCall(id="fc_0", call_id=f"call_{len(self.calls)}", name="search_clauses",
                                            arguments=json.dumps({"query": "collision"}), type="function_call")
            return self._respond([call])
        file = parse_claim_file(input)
        queries = _QUERIES.get(self.stage)
        if queries and not _tool_outputs(input):
            planned = queries(file)
            if planned:
                calls = [ResponseFunctionToolCall(id=f"fc_{i}", call_id=f"call_{i}", name="search_clauses",
                                                  arguments=json.dumps({"query": q}), type="function_call")
                         for i, q in enumerate(planned)]
                return self._respond(calls)
        answer = _RESPONDERS[self.stage](file, input)
        if fault and fault.kind == "invent_citation":
            answer["cited_clause_ids"] = [*answer["cited_clause_ids"], "CLS-XXX-999"]
        if fault and fault.kind == "foreign_claim":
            answer["reasoning"] += " See also CLM-2026-0999."
        return self._respond([_message(json.dumps(answer))])

    @staticmethod
    def _respond(output: list) -> ModelResponse:
        return ModelResponse(output=output, usage=Usage(requests=1, input_tokens=10, output_tokens=1), response_id=None)

    def stream_response(self, *args, **kwargs) -> AsyncIterator:
        raise NotImplementedError("the pipeline does not stream the mock brain")


@dataclass
class MockBrain:
    """Deterministic stand-in for the models."""

    fault: Fault | None = None
    calls: list[str] = field(default_factory=list)
    name: str = "mock"

    def model(self, stage: str) -> Model:
        return MockModel(stage, self.fault, self.calls)

    def model_id(self, stage: str) -> str:
        return f"mock-brain/{stage}"


@dataclass
class OpenAIBrain:
    """The real models, routed per stage (D-017). The SDK reads OPENAI_API_KEY from the environment."""

    name: str = "openai"

    def model(self, stage: str) -> str:
        return MODEL_ROUTING[stage]

    def model_id(self, stage: str) -> str:
        return MODEL_ROUTING[stage]


def brain_from_name(name: str):
    if name == "mock":
        return MockBrain()
    if name == "openai":
        return OpenAIBrain()
    raise ValueError(f"unknown brain {name!r}; use mock or openai")
