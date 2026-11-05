"""Local trace capture for the Agents SDK.

Replaces the SDK's default exporter, so traces stay here instead of going to the shared IK OpenAI
organization. Each run's spans (agents, model calls, tool calls, and the deterministic stages) can be
read back by trace ID after the fact.
"""

from __future__ import annotations

import threading

from agents import TracingProcessor, set_trace_processors

_MAX_TRACES = 200


class LocalTraceStore(TracingProcessor):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._spans: dict[str, list[dict]] = {}

    def on_trace_start(self, trace) -> None:
        with self._lock:
            self._spans[trace.trace_id] = []
            while len(self._spans) > _MAX_TRACES:
                self._spans.pop(next(iter(self._spans)))

    def on_trace_end(self, trace) -> None:
        return None

    def on_span_start(self, span) -> None:
        return None

    def on_span_end(self, span) -> None:
        data = span.span_data.export()
        data.pop("input", None)  # the prompt repeats the whole claim file; the file is in the fixtures
        record = {"span_id": span.span_id, "parent_id": span.parent_id, "started_at": span.started_at,
                  "ended_at": span.ended_at, "data": data, "error": span.error}
        with self._lock:
            self._spans.setdefault(span.trace_id, []).append(record)

    def spans(self, trace_id: str) -> list[dict]:
        with self._lock:
            return sorted(self._spans.get(trace_id, []), key=lambda s: s["started_at"] or "")

    def shutdown(self) -> None:
        return None

    def force_flush(self) -> None:
        return None


_store = LocalTraceStore()


def install_local_tracing() -> LocalTraceStore:
    set_trace_processors([_store])
    return _store
