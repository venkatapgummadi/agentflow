"""
Tracer — minimal OpenTelemetry-style tracing without external deps.

Provides `Tracer` and `Span` with parent/child relationships,
status, attributes, and events. Designed to be a drop-in shim that
can later be replaced with the real `opentelemetry-api` package
without changing call sites.

Usage:
    tracer = Tracer(service_name="agentflow")

    with tracer.start_span("orchestrator.execute", kind=SpanKind.INTERNAL) as root:
        with tracer.start_span("connector.invoke", kind=SpanKind.CLIENT) as child:
            child.set_attribute("connector.id", "mulesoft-crm")
            child.add_event("request.sent")
            ...
            child.set_status(SpanStatus.OK)

    spans = tracer.finished_spans  # list[Span] — for export

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SpanKind(Enum):
    """Span kind categories (mirrors the OTel taxonomy)."""

    INTERNAL = "internal"
    CLIENT = "client"
    SERVER = "server"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class SpanStatus(Enum):
    """Outcome status for a span."""

    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


@dataclass
class SpanEvent:
    """Timed annotation attached to a span."""

    name: str
    timestamp: float = field(default_factory=time.time)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Span:
    """A unit of work tracked by the tracer."""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    kind: SpanKind = SpanKind.INTERNAL
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    status: SpanStatus = SpanStatus.UNSET
    status_message: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[SpanEvent] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000.0

    @property
    def is_finished(self) -> bool:
        return self.end_time is not None

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        self.attributes.update(attributes)

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        self.events.append(SpanEvent(name=name, attributes=attributes or {}))

    def set_status(self, status: SpanStatus, message: str = "") -> None:
        self.status = status
        if message:
            self.status_message = message

    def record_exception(self, exc: BaseException) -> None:
        self.set_status(SpanStatus.ERROR, message=str(exc))
        self.add_event(
            "exception",
            attributes={
                "exception.type": type(exc).__name__,
                "exception.message": str(exc),
            },
        )

    def end(self) -> None:
        if self.end_time is None:
            self.end_time = time.time()
            if self.status == SpanStatus.UNSET:
                self.status = SpanStatus.OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "kind": self.kind.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round(self.duration_ms, 4),
            "status": self.status.value,
            "status_message": self.status_message,
            "attributes": dict(self.attributes),
            "events": [
                {
                    "name": e.name,
                    "timestamp": e.timestamp,
                    "attributes": dict(e.attributes),
                }
                for e in self.events
            ],
        }


class Tracer:
    """
    Lightweight tracer with thread-local span stack.

    Args:
        service_name: Logical service identifier added to every span.
        max_finished_spans: Cap on retained finished spans (FIFO eviction).
    """

    def __init__(
        self,
        service_name: str = "agentflow",
        max_finished_spans: int = 1024,
    ):
        if max_finished_spans <= 0:
            raise ValueError("max_finished_spans must be > 0")
        self.service_name = service_name
        self.max_finished_spans = max_finished_spans
        self._finished: list[Span] = []
        self._lock = threading.RLock()
        self._local = threading.local()

    @property
    def finished_spans(self) -> list[Span]:
        """Snapshot of finished spans (oldest first)."""
        with self._lock:
            return list(self._finished)

    def current_span(self) -> Span | None:
        """Return the innermost active span on this thread."""
        stack: list[Span] | None = getattr(self._local, "stack", None)
        if not stack:
            return None
        return stack[-1]

    @contextmanager
    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[Span]:
        """Start a new span as a child of the current one (if any)."""
        parent = self.current_span()
        trace_id = parent.trace_id if parent else uuid.uuid4().hex
        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=uuid.uuid4().hex[:16],
            parent_span_id=parent.span_id if parent else None,
            kind=kind,
            attributes={"service.name": self.service_name, **(attributes or {})},
        )

        stack = getattr(self._local, "stack", None)
        if stack is None:
            stack = []
            self._local.stack = stack
        stack.append(span)

        try:
            yield span
        except BaseException as exc:  # noqa: BLE001 — record + re-raise
            span.record_exception(exc)
            raise
        finally:
            span.end()
            stack.pop()
            self._record(span)

    def shutdown(self) -> list[dict[str, Any]]:
        """Drain and return all finished spans as dicts."""
        with self._lock:
            spans = [s.to_dict() for s in self._finished]
            self._finished.clear()
        return spans

    # ── Internal ─────────────────────────────────────────────────────────

    def _record(self, span: Span) -> None:
        with self._lock:
            if len(self._finished) >= self.max_finished_spans:
                self._finished.pop(0)
            self._finished.append(span)
