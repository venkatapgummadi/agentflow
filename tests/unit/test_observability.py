"""
Tests for the Tracer and MetricsCollector.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import pytest

from agentflow.observability.metrics import MetricsCollector
from agentflow.observability.tracer import (
    SpanKind,
    SpanStatus,
    Tracer,
)


class TestTracerBasic:
    def test_root_span_is_recorded(self):
        tracer = Tracer(service_name="svc")
        with tracer.start_span("op") as span:
            assert span.parent_span_id is None
            assert span.kind == SpanKind.INTERNAL
        spans = tracer.finished_spans
        assert len(spans) == 1
        assert spans[0].status == SpanStatus.OK
        assert spans[0].duration_ms >= 0.0

    def test_child_inherits_trace_id(self):
        tracer = Tracer()
        trace_ids: list[str] = []
        parent_ids: list[str | None] = []
        with tracer.start_span("parent") as parent:
            trace_ids.append(parent.trace_id)
            parent_ids.append(parent.parent_span_id)
            with tracer.start_span("child") as child:
                trace_ids.append(child.trace_id)
                parent_ids.append(child.parent_span_id)
        assert trace_ids[0] == trace_ids[1]
        assert parent_ids[0] is None
        assert parent_ids[1] is not None

    def test_attributes_and_events(self):
        tracer = Tracer()
        with tracer.start_span("op") as span:
            span.set_attribute("k", "v")
            span.set_attributes({"a": 1, "b": 2})
            span.add_event("started", {"phase": "init"})
        finished = tracer.finished_spans[0]
        assert finished.attributes["k"] == "v"
        assert finished.attributes["a"] == 1
        assert finished.events[0].name == "started"
        assert finished.events[0].attributes["phase"] == "init"

    def test_exception_marks_error_and_propagates(self):
        tracer = Tracer()

        with pytest.raises(RuntimeError):
            with tracer.start_span("op"):
                raise RuntimeError("boom")

        finished = tracer.finished_spans[0]
        assert finished.status == SpanStatus.ERROR
        assert "boom" in finished.status_message
        # The exception event was recorded
        assert any(e.name == "exception" for e in finished.events)

    def test_shutdown_drains_spans(self):
        tracer = Tracer()
        with tracer.start_span("a"):
            pass
        with tracer.start_span("b"):
            pass
        drained = tracer.shutdown()
        assert len(drained) == 2
        assert tracer.finished_spans == []

    def test_max_finished_spans_eviction(self):
        tracer = Tracer(max_finished_spans=2)
        for name in ("a", "b", "c"):
            with tracer.start_span(name):
                pass
        names = [s.name for s in tracer.finished_spans]
        assert names == ["b", "c"]


class TestMetricsCollector:
    def test_counter_inc_and_get(self):
        m = MetricsCollector()
        m.inc("requests")
        m.inc("requests", amount=2.0)
        assert m.get_counter("requests") == 3.0

    def test_counter_with_labels_isolated(self):
        m = MetricsCollector()
        m.inc("requests", labels={"connector": "rest"})
        m.inc("requests", labels={"connector": "graphql"}, amount=4)
        assert m.get_counter("requests", labels={"connector": "rest"}) == 1.0
        assert m.get_counter("requests", labels={"connector": "graphql"}) == 4.0

    def test_counter_rejects_negative(self):
        m = MetricsCollector()
        with pytest.raises(ValueError):
            m.inc("requests", amount=-1)

    def test_gauge_set_and_get(self):
        m = MetricsCollector()
        m.set_gauge("queue_depth", 5)
        m.set_gauge("queue_depth", 7)
        assert m.get_gauge("queue_depth") == 7.0

    def test_histogram_observe_and_snapshot(self):
        m = MetricsCollector()
        for v in (10, 20, 30, 40, 50):
            m.observe("latency_ms", v)
        snap = m.get_histogram("latency_ms")
        assert snap is not None
        assert snap["count"] == 5
        assert snap["sum"] == 150.0
        assert snap["min"] == 10.0
        assert snap["max"] == 50.0
        # Bucket counts should be monotonic non-decreasing
        cumulative = 0
        for bucket in snap["buckets"][:-1]:
            cumulative = max(cumulative, bucket["count"])

    def test_full_snapshot_shape(self):
        m = MetricsCollector()
        m.inc("c")
        m.set_gauge("g", 3)
        m.observe("h", 1.0)
        snap = m.snapshot()
        assert "counters" in snap
        assert "gauges" in snap
        assert "histograms" in snap

    def test_reset_clears_everything(self):
        m = MetricsCollector()
        m.inc("c")
        m.set_gauge("g", 1)
        m.observe("h", 1.0)
        m.reset()
        snap = m.snapshot()
        assert snap == {"counters": {}, "gauges": {}, "histograms": {}}
