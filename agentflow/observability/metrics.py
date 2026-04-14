"""
MetricsCollector — counters, gauges, and histograms without dependencies.

Mirrors the surface of common metrics libraries (Prometheus, OTel
metrics) so it can be swapped in production without changing call
sites. All operations are thread-safe.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Any


def _label_key(labels: dict[str, str] | None) -> str:
    if not labels:
        return ""
    return "|".join(f"{k}={labels[k]}" for k in sorted(labels))


@dataclass
class _Histogram:
    """Bucketed histogram with a small, fixed default bucket layout."""

    buckets: tuple[float, ...] = (
        5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000,
    )
    counts: list[int] = field(default_factory=list)
    sum_value: float = 0.0
    count: int = 0
    min_value: float = math.inf
    max_value: float = -math.inf

    def __post_init__(self) -> None:
        if not self.counts:
            self.counts = [0] * (len(self.buckets) + 1)

    def observe(self, value: float) -> None:
        self.sum_value += value
        self.count += 1
        self.min_value = min(self.min_value, value)
        self.max_value = max(self.max_value, value)
        for i, bound in enumerate(self.buckets):
            if value <= bound:
                self.counts[i] += 1
                return
        self.counts[-1] += 1

    def snapshot(self) -> dict[str, Any]:
        avg = self.sum_value / self.count if self.count else 0.0
        return {
            "count": self.count,
            "sum": round(self.sum_value, 4),
            "avg": round(avg, 4),
            "min": 0.0 if self.count == 0 else round(self.min_value, 4),
            "max": 0.0 if self.count == 0 else round(self.max_value, 4),
            "buckets": [
                {"le": str(b), "count": self.counts[i]}
                for i, b in enumerate(self.buckets)
            ]
            + [{"le": "+Inf", "count": self.counts[-1]}],
        }


class MetricsCollector:
    """
    Thread-safe counters, gauges, and histograms.

    Usage:
        metrics = MetricsCollector()
        metrics.inc("requests_total", labels={"connector": "mulesoft"})
        metrics.set_gauge("queue_depth", 4, labels={"queue": "ingest"})
        metrics.observe("latency_ms", 142.0, labels={"endpoint": "GET /x"})
        snapshot = metrics.snapshot()
    """

    def __init__(self) -> None:
        self._counters: dict[str, dict[str, float]] = {}
        self._gauges: dict[str, dict[str, float]] = {}
        self._histograms: dict[str, dict[str, _Histogram]] = {}
        self._lock = threading.RLock()

    # ── Counters ─────────────────────────────────────────────────────────

    def inc(
        self,
        name: str,
        amount: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        if amount < 0:
            raise ValueError("counters can only increase; got amount < 0")
        key = _label_key(labels)
        with self._lock:
            bucket = self._counters.setdefault(name, {})
            bucket[key] = bucket.get(key, 0.0) + amount

    def get_counter(
        self, name: str, labels: dict[str, str] | None = None
    ) -> float:
        with self._lock:
            return self._counters.get(name, {}).get(_label_key(labels), 0.0)

    # ── Gauges ───────────────────────────────────────────────────────────

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        with self._lock:
            self._gauges.setdefault(name, {})[_label_key(labels)] = float(value)

    def get_gauge(
        self, name: str, labels: dict[str, str] | None = None
    ) -> float:
        with self._lock:
            return self._gauges.get(name, {}).get(_label_key(labels), 0.0)

    # ── Histograms ───────────────────────────────────────────────────────

    def observe(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        key = _label_key(labels)
        with self._lock:
            bucket = self._histograms.setdefault(name, {})
            hist = bucket.get(key) or _Histogram()
            hist.observe(float(value))
            bucket[key] = hist

    def get_histogram(
        self, name: str, labels: dict[str, str] | None = None
    ) -> dict[str, Any] | None:
        with self._lock:
            hist = self._histograms.get(name, {}).get(_label_key(labels))
            return hist.snapshot() if hist else None

    # ── Snapshot ─────────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """Read-consistent snapshot of all metrics."""
        with self._lock:
            return {
                "counters": {
                    name: dict(values) for name, values in self._counters.items()
                },
                "gauges": {
                    name: dict(values) for name, values in self._gauges.items()
                },
                "histograms": {
                    name: {label: hist.snapshot() for label, hist in by_label.items()}
                    for name, by_label in self._histograms.items()
                },
            }

    def reset(self) -> None:
        """Clear all stored metrics."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
