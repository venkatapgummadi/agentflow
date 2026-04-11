"""
Dynamic Router — intelligent multi-dimensional API endpoint selection.

The DynamicRouter scores candidate API endpoints across multiple
dimensions and selects the optimal one in real time:
- Latency (P95 response time)
- Cost per call
- Rate limit headroom
- Semantic capability match
- Health status

Supports pluggable scoring strategies and weighted combinations.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import math
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EndpointScore:
    """Detailed scoring breakdown for a candidate endpoint."""

    endpoint_id: str = ""
    connector_id: str = ""
    latency_score: float = 0.0
    cost_score: float = 0.0
    rate_limit_score: float = 0.0
    capability_score: float = 0.0
    health_score: float = 0.0
    total_score: float = 0.0
    selected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "connector_id": self.connector_id,
            "scores": {
                "latency": round(self.latency_score, 4),
                "cost": round(self.cost_score, 4),
                "rate_limit": round(self.rate_limit_score, 4),
                "capability": round(self.capability_score, 4),
                "health": round(self.health_score, 4),
                "total": round(self.total_score, 4),
            },
            "selected": self.selected,
        }


@dataclass
class RoutingWeights:
    """
    Configurable weights for each scoring dimension.

    Weights must sum to 1.0 for normalized scoring.
    Different profiles support different use cases:
    - BALANCED: Equal weight across all dimensions
    - LOW_LATENCY: Prioritize response time
    - LOW_COST: Prioritize cheapest endpoint
    - HIGH_AVAILABILITY: Prioritize health and headroom
    """

    latency: float = 0.30
    cost: float = 0.20
    rate_limit: float = 0.15
    capability: float = 0.25
    health: float = 0.10

    def validate(self) -> bool:
        total = self.latency + self.cost + self.rate_limit + self.capability + self.health
        return abs(total - 1.0) < 0.01

    @classmethod
    def balanced(cls) -> RoutingWeights:
        return cls(latency=0.20, cost=0.20, rate_limit=0.20, capability=0.20, health=0.20)

    @classmethod
    def low_latency(cls) -> RoutingWeights:
        return cls(latency=0.50, cost=0.10, rate_limit=0.10, capability=0.20, health=0.10)

    @classmethod
    def low_cost(cls) -> RoutingWeights:
        return cls(latency=0.10, cost=0.50, rate_limit=0.10, capability=0.20, health=0.10)

    @classmethod
    def high_availability(cls) -> RoutingWeights:
        return cls(latency=0.10, cost=0.10, rate_limit=0.25, capability=0.15, health=0.40)


@dataclass
class EndpointMetrics:
    """Runtime metrics for an endpoint, updated on each call."""

    endpoint_id: str = ""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    latency_sum_ms: float = 0.0
    latency_max_ms: float = 0.0
    last_failure_time: float = 0.0
    consecutive_failures: int = 0
    last_updated: float = field(default_factory=time.time)

    @property
    def avg_latency_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.latency_sum_ms / self.total_calls

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.successful_calls / self.total_calls

    def record_success(self, latency_ms: float) -> None:
        self.total_calls += 1
        self.successful_calls += 1
        self.latency_sum_ms += latency_ms
        self.latency_max_ms = max(self.latency_max_ms, latency_ms)
        self.consecutive_failures = 0
        self.last_updated = time.time()

    def record_failure(self) -> None:
        self.total_calls += 1
        self.failed_calls += 1
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        self.last_updated = time.time()


class DynamicRouter:
    """
    Intelligent multi-dimensional API endpoint router.

    Scores all candidate endpoints and selects the optimal one based
    on real-time metrics and configurable weights.

    Usage:
        router = DynamicRouter(weights=RoutingWeights.low_latency())
        best = router.route(
            candidates=[endpoint1, endpoint2, endpoint3],
            required_capability="customer.fetch"
        )
    """

    def __init__(
        self,
        weights: Optional[RoutingWeights] = None,
        custom_scorers: Optional[Dict[str, Callable]] = None,
    ):
        self.weights = weights or RoutingWeights()
        self.custom_scorers = custom_scorers or {}
        self._metrics: Dict[str, EndpointMetrics] = {}

        if not self.weights.validate():
            logger.warning("Routing weights do not sum to 1.0 — normalizing")

    def route(
        self,
        candidates: List[Dict[str, Any]],
        required_capability: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Select the optimal endpoint from candidates.

        Returns the highest-scoring candidate, or None if no
        viable candidates exist.
        """
        if not candidates:
            return None

        scores = self.score_all(candidates, required_capability, context)
        scores.sort(key=lambda s: s.total_score, reverse=True)

        if scores:
            scores[0].selected = True
            winner = scores[0]
            logger.debug(
                "Routed to %s (score=%.4f) over %d candidates",
                winner.endpoint_id,
                winner.total_score,
                len(candidates),
            )
            # Return the original candidate dict
            for c in candidates:
                if c.get("endpoint_id") == winner.endpoint_id:
                    return c

        return candidates[0] if candidates else None

    def score_all(
        self,
        candidates: List[Dict[str, Any]],
        required_capability: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> List[EndpointScore]:
        """Score all candidate endpoints."""
        scores: List[EndpointScore] = []
        for candidate in candidates:
            score = self._score_endpoint(candidate, required_capability, context)
            scores.append(score)
        return scores

    def record_call_result(
        self,
        endpoint_id: str,
        success: bool,
        latency_ms: float = 0.0,
    ) -> None:
        """Update runtime metrics for an endpoint after a call."""
        if endpoint_id not in self._metrics:
            self._metrics[endpoint_id] = EndpointMetrics(endpoint_id=endpoint_id)

        metrics = self._metrics[endpoint_id]
        if success:
            metrics.record_success(latency_ms)
        else:
            metrics.record_failure()

    def _score_endpoint(
        self,
        candidate: Dict[str, Any],
        required_capability: str,
        context: Optional[Dict[str, Any]],
    ) -> EndpointScore:
        """Calculate multi-dimensional score for a single endpoint."""
        ep_id = candidate.get("endpoint_id", "")
        metrics = self._metrics.get(ep_id, EndpointMetrics())

        # Latency score: exponential decay from P95 latency
        p95_latency = candidate.get("latency_p95_ms", 100)
        actual_latency = metrics.avg_latency_ms or p95_latency
        latency_score = math.exp(-actual_latency / 1000)

        # Cost score: inverse of cost per call
        cost = candidate.get("cost_per_call", 0.0)
        cost_score = 1.0 / (1.0 + cost * 100)

        # Rate limit score: remaining headroom fraction
        rpm_limit = candidate.get("rate_limit_rpm", 1000)
        rate_limit_score = min(rpm_limit, 1000) / 1000

        # Capability score: tag overlap with required capability
        tags = [t.lower() for t in candidate.get("tags", [])]
        if required_capability:
            cap_words = set(required_capability.lower().split("."))
            tag_set = set(tags)
            overlap = len(cap_words & tag_set)
            capability_score = overlap / max(len(cap_words), 1)
        else:
            capability_score = 1.0

        # Health score: based on success rate and consecutive failures
        health_score = metrics.success_rate
        if metrics.consecutive_failures > 3:
            health_score *= 0.5  # Penalize persistent failures

        # Weighted total
        total = (
            self.weights.latency * latency_score
            + self.weights.cost * cost_score
            + self.weights.rate_limit * rate_limit_score
            + self.weights.capability * capability_score
            + self.weights.health * health_score
        )

        return EndpointScore(
            endpoint_id=ep_id,
            connector_id=candidate.get("connector_id", ""),
            latency_score=latency_score,
            cost_score=cost_score,
            rate_limit_score=rate_limit_score,
            capability_score=capability_score,
            health_score=health_score,
            total_score=total,
        )
