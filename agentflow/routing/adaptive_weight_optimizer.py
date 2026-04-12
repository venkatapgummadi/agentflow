"""
Adaptive Weight Optimizer for Multi-Dimensional API Routing.

This module extends the DynamicRouter's scoring system with self-tuning
weight optimization. Instead of relying on statically configured weights
for the five routing dimensions (latency, cost, rate-limit headroom,
capability match, health status), the optimizer continuously adjusts
weights based on observed API performance and SLA compliance.

Algorithm:
    Uses Exponential Moving Average (EMA) tracking with gradient-free
    optimization and momentum to adjust weights when SLA violations
    are detected. Violated dimensions receive higher weight, causing
    the DynamicRouter to prioritize them in subsequent decisions.

References:
    - AgentFlow Paper, Section 3.2: Multi-Dimensional Routing Engine
    - AgentFlow Paper, Equation 1: Composite Routing Score

Author: Venkata Pavan Kumar Gummadi
License: Apache 2.0
"""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RoutingDimension(Enum):
    """Five routing dimensions as defined in the AgentFlow architecture."""

    LATENCY = "latency"
    COST = "cost"
    RATE_LIMIT_HEADROOM = "rate_limit_headroom"
    CAPABILITY_MATCH = "capability_match"
    HEALTH_STATUS = "health_status"


@dataclass
class DimensionSLA:
    """SLA threshold for a single routing dimension."""

    dimension: RoutingDimension
    target: float
    tolerance: float = 0.1

    @property
    def upper_bound(self) -> float:
        return self.target * (1.0 + self.tolerance)

    @property
    def lower_bound(self) -> float:
        return self.target * (1.0 - self.tolerance)


@dataclass
class EndpointPerformanceSnapshot:
    """Point-in-time performance observation for an API endpoint."""

    endpoint_id: str
    timestamp: float
    latency_ms: float
    cost_per_call: float
    rate_limit_remaining_pct: float
    capability_score: float
    health_score: float


@dataclass
class WeightState:
    """Current optimized weights and metadata."""

    weights: dict[RoutingDimension, float]
    last_updated: float = 0.0
    adjustment_count: int = 0
    sla_violations: dict[RoutingDimension, int] = field(
        default_factory=lambda: defaultdict(int)
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize weight state for monitoring and logging."""
        return {
            "weights": {d.value: round(w, 4) for d, w in self.weights.items()},
            "last_updated": self.last_updated,
            "adjustment_count": self.adjustment_count,
            "sla_violations": {
                d.value: c for d, c in self.sla_violations.items()
            },
        }


class AdaptiveWeightOptimizer:
    """
    Continuously optimizes routing weights based on observed performance.

    Works alongside the existing DynamicRouter: the optimizer monitors
    endpoint performance and provides optimized weight vectors that the
    router uses for its multi-dimensional scoring.

    Algorithm:
        1. Observe endpoint performance snapshots from completed API calls
        2. Compute EMA-smoothed scores per dimension per endpoint
        3. Detect SLA violations using configured thresholds
        4. Apply weight adjustments using gradient-free optimization:
           - Increase weight for violated dimensions
           - Normalize weights to maintain sum = 1.0
           - Apply momentum to prevent oscillation
        5. Emit updated weights for the DynamicRouter

    Example:
        >>> optimizer = AdaptiveWeightOptimizer(
        ...     sla_config={
        ...         RoutingDimension.LATENCY: DimensionSLA(
        ...             RoutingDimension.LATENCY, target=100.0
        ...         ),
        ...     },
        ... )
        >>> snapshot = EndpointPerformanceSnapshot(
        ...     endpoint_id="payments-v2",
        ...     timestamp=time.time(),
        ...     latency_ms=150.0,
        ...     cost_per_call=0.002,
        ...     rate_limit_remaining_pct=0.45,
        ...     capability_score=0.92,
        ...     health_score=1.0,
        ... )
        >>> optimizer.observe(snapshot)
        >>> weights = optimizer.get_current_weights()
    """

    DEFAULT_WEIGHTS: dict[RoutingDimension, float] = {
        RoutingDimension.LATENCY: 0.30,
        RoutingDimension.COST: 0.20,
        RoutingDimension.RATE_LIMIT_HEADROOM: 0.15,
        RoutingDimension.CAPABILITY_MATCH: 0.20,
        RoutingDimension.HEALTH_STATUS: 0.15,
    }

    MIN_WEIGHT = 0.05
    MAX_WEIGHT = 0.50

    def __init__(
        self,
        sla_config: dict[RoutingDimension, DimensionSLA] | None = None,
        initial_weights: dict[RoutingDimension, float] | None = None,
        ema_decay: float = 0.95,
        learning_rate: float = 0.05,
        momentum: float = 0.8,
        adjustment_interval_seconds: float = 60.0,
    ) -> None:
        self._sla_config = sla_config or {}
        self._ema_decay = ema_decay
        self._learning_rate = learning_rate
        self._momentum = momentum
        self._adjustment_interval = adjustment_interval_seconds

        weights = initial_weights or self.DEFAULT_WEIGHTS.copy()
        self._state = WeightState(weights=weights, last_updated=time.time())
        self._ema_scores: dict[str, dict[RoutingDimension, float]] = defaultdict(dict)
        self._velocity: dict[RoutingDimension, float] = {
            dim: 0.0 for dim in RoutingDimension
        }
        self._observation_buffer: list[EndpointPerformanceSnapshot] = []

        logger.info(
            "AdaptiveWeightOptimizer initialized | weights=%s | "
            "ema_decay=%.3f | lr=%.3f | momentum=%.3f",
            {d.value: round(w, 3) for d, w in weights.items()},
            ema_decay,
            learning_rate,
            momentum,
        )

    def observe(self, snapshot: EndpointPerformanceSnapshot) -> None:
        """Record a performance observation and trigger optimization if due."""
        self._update_ema(snapshot)
        self._observation_buffer.append(snapshot)

        elapsed = time.time() - self._state.last_updated
        if elapsed >= self._adjustment_interval:
            self._run_optimization()

    def observe_batch(self, snapshots: list[EndpointPerformanceSnapshot]) -> None:
        """Record multiple observations and trigger optimization."""
        for snapshot in snapshots:
            self._update_ema(snapshot)
            self._observation_buffer.append(snapshot)
        self._run_optimization()

    def get_current_weights(self) -> dict[RoutingDimension, float]:
        """Return current optimized routing weights."""
        return self._state.weights.copy()

    def get_weights_as_tuple(self) -> tuple[float, float, float, float, float]:
        """Return weights as ordered tuple for DynamicRouter integration."""
        w = self._state.weights
        return (
            w[RoutingDimension.LATENCY],
            w[RoutingDimension.COST],
            w[RoutingDimension.RATE_LIMIT_HEADROOM],
            w[RoutingDimension.CAPABILITY_MATCH],
            w[RoutingDimension.HEALTH_STATUS],
        )

    def get_weight_state(self) -> WeightState:
        """Return full weight state including metadata."""
        return self._state

    def reset(self) -> None:
        """Reset optimizer to initial default state."""
        self._state = WeightState(
            weights=self.DEFAULT_WEIGHTS.copy(), last_updated=time.time()
        )
        self._ema_scores.clear()
        self._velocity = {dim: 0.0 for dim in RoutingDimension}
        self._observation_buffer.clear()
        logger.info("AdaptiveWeightOptimizer reset to defaults")

    def _update_ema(self, snapshot: EndpointPerformanceSnapshot) -> None:
        """Update EMA-smoothed scores for the observed endpoint."""
        endpoint = snapshot.endpoint_id
        dimension_values = {
            RoutingDimension.LATENCY: snapshot.latency_ms,
            RoutingDimension.COST: snapshot.cost_per_call,
            RoutingDimension.RATE_LIMIT_HEADROOM: snapshot.rate_limit_remaining_pct,
            RoutingDimension.CAPABILITY_MATCH: snapshot.capability_score,
            RoutingDimension.HEALTH_STATUS: snapshot.health_score,
        }

        for dim, value in dimension_values.items():
            if dim in self._ema_scores[endpoint]:
                old = self._ema_scores[endpoint][dim]
                self._ema_scores[endpoint][dim] = (
                    self._ema_decay * old + (1.0 - self._ema_decay) * value
                )
            else:
                self._ema_scores[endpoint][dim] = value

    def _detect_violations(self) -> dict[RoutingDimension, float]:
        """Detect SLA violations and return violation magnitudes."""
        violations: dict[RoutingDimension, float] = {}

        for dim, sla in self._sla_config.items():
            violation_sum = 0.0
            violation_count = 0

            for endpoint, scores in self._ema_scores.items():
                if dim not in scores:
                    continue

                current = scores[dim]
                if dim in (RoutingDimension.LATENCY, RoutingDimension.COST):
                    if current > sla.upper_bound:
                        violation_sum += (current - sla.target) / sla.target
                        violation_count += 1
                else:
                    if current < sla.lower_bound:
                        violation_sum += (sla.target - current) / sla.target
                        violation_count += 1

            if violation_count > 0:
                violations[dim] = violation_sum / violation_count
                self._state.sla_violations[dim] += violation_count

        return violations

    def _run_optimization(self) -> None:
        """Execute one optimization round with momentum-based updates."""
        violations = self._detect_violations()

        if not violations:
            self._observation_buffer.clear()
            self._state.last_updated = time.time()
            return

        logger.info(
            "SLA violations detected: %s",
            {d.value: round(v, 4) for d, v in violations.items()},
        )

        gradient: dict[RoutingDimension, float] = {}
        for dim in RoutingDimension:
            if dim in violations:
                gradient[dim] = violations[dim] * self._learning_rate
            else:
                gradient[dim] = -self._learning_rate * 0.1

        for dim in RoutingDimension:
            self._velocity[dim] = (
                self._momentum * self._velocity[dim] + gradient.get(dim, 0.0)
            )

        new_weights: dict[RoutingDimension, float] = {}
        for dim in RoutingDimension:
            new_w = self._state.weights[dim] + self._velocity[dim]
            new_w = max(self.MIN_WEIGHT, min(self.MAX_WEIGHT, new_w))
            new_weights[dim] = new_w

        total = sum(new_weights.values())
        new_weights = {d: w / total for d, w in new_weights.items()}

        old_weights = self._state.weights
        self._state.weights = new_weights
        self._state.last_updated = time.time()
        self._state.adjustment_count += 1

        logger.info(
            "Weights adjusted (round %d): %s -> %s",
            self._state.adjustment_count,
            {d.value: round(w, 3) for d, w in old_weights.items()},
            {d.value: round(w, 3) for d, w in new_weights.items()},
        )
        self._observation_buffer.clear()

    def compute_composite_score(
        self,
        latency_score: float,
        cost_score: float,
        headroom_score: float,
        capability_score: float,
        health_score: float,
    ) -> float:
        """
        Compute composite routing score using current optimized weights.

        Implements Equation 1 from the AgentFlow paper:
            S(e) = sum(w_i * normalize(d_i(e)))

        All inputs should be normalized to [0.0, 1.0], higher = better.
        """
        w = self._state.weights
        return (
            w[RoutingDimension.LATENCY] * latency_score
            + w[RoutingDimension.COST] * cost_score
            + w[RoutingDimension.RATE_LIMIT_HEADROOM] * headroom_score
            + w[RoutingDimension.CAPABILITY_MATCH] * capability_score
            + w[RoutingDimension.HEALTH_STATUS] * health_score
        )
