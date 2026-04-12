"""
Exponential Cooldown Strategy for the Adaptive Circuit Breaker.

Extends the existing CircuitBreaker with a learning-based cooldown
algorithm. Instead of fixed recovery timeouts, this strategy adjusts
cooldown duration based on per-endpoint failure and recovery patterns.

Algorithm (from AgentFlow Paper, Section 4.2):
    cooldown(n) = base_cooldown * decay_factor^n * jitter

Where decay_factor is learned:
    - Recovery success → decay decreases (faster future recovery)
    - Recovery failure → decay increases (more cautious)

Author: Venkata Pavan Kumar Gummadi
License: Apache 2.0
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass
from typing import Any

from agentflow.resilience.circuit_breaker import CircuitState

logger = logging.getLogger(__name__)


@dataclass
class CooldownMetrics:
    """Per-endpoint cooldown metrics and learned parameters."""

    endpoint_id: str
    consecutive_failures: int = 0
    total_failures: int = 0
    total_recoveries: int = 0
    last_failure_time: float = 0.0
    last_recovery_time: float = 0.0
    current_cooldown_ms: float = 0.0
    learned_decay_factor: float = 2.0
    recovery_success_rate: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize metrics for monitoring."""
        return {
            "endpoint_id": self.endpoint_id,
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "total_recoveries": self.total_recoveries,
            "current_cooldown_ms": round(self.current_cooldown_ms, 1),
            "learned_decay_factor": round(self.learned_decay_factor, 3),
            "recovery_success_rate": round(self.recovery_success_rate, 3),
        }


class ExponentialCooldownStrategy:
    """
    Adaptive cooldown with exponential backoff and learned decay factors.

    Integrates with the existing CircuitBreaker to provide intelligent
    cooldown timing. Each endpoint independently learns its optimal
    recovery timing based on historical outcomes.

    Learning rules:
        Success → decay_factor *= (1 - 0.1) → shorter future cooldowns
        Failure → decay_factor *= (1 + 0.2) → longer future cooldowns

    The asymmetric rates encode conservative bias: the system becomes
    cautious faster than it becomes optimistic.

    Example:
        >>> strategy = ExponentialCooldownStrategy(base_cooldown_ms=1000)
        >>> cooldown = strategy.record_failure("payments-api")
        >>> if strategy.should_attempt_recovery("payments-api"):
        ...     strategy.record_recovery_success("payments-api")
    """

    MIN_DECAY_FACTOR = 1.5
    MAX_DECAY_FACTOR = 10.0
    SUCCESS_LEARNING_RATE = 0.1
    FAILURE_LEARNING_RATE = 0.2

    def __init__(
        self,
        base_cooldown_ms: float = 1000.0,
        max_cooldown_ms: float = 300_000.0,
        jitter_factor: float = 0.1,
        failure_threshold: int = 3,
        half_open_max_requests: int = 1,
    ) -> None:
        self._base_cooldown_ms = base_cooldown_ms
        self._max_cooldown_ms = max_cooldown_ms
        self._jitter_factor = jitter_factor
        self._failure_threshold = failure_threshold
        self._half_open_max_requests = half_open_max_requests

        self._metrics: dict[str, CooldownMetrics] = {}
        self._circuit_states: dict[str, CircuitState] = {}

        logger.info(
            "ExponentialCooldownStrategy initialized | base=%dms | "
            "max=%dms | threshold=%d",
            base_cooldown_ms,
            max_cooldown_ms,
            failure_threshold,
        )

    def get_circuit_state(self, endpoint_id: str) -> CircuitState:
        """Get current circuit state for an endpoint."""
        return self._circuit_states.get(endpoint_id, CircuitState.CLOSED)

    def get_metrics(self, endpoint_id: str) -> CooldownMetrics | None:
        """Get cooldown metrics for an endpoint."""
        return self._metrics.get(endpoint_id)

    def get_all_metrics(self) -> dict[str, CooldownMetrics]:
        """Get cooldown metrics for all tracked endpoints."""
        return self._metrics.copy()

    def record_failure(self, endpoint_id: str) -> float:
        """
        Record an endpoint failure and compute cooldown.

        Returns:
            Cooldown duration in milliseconds before next retry.
        """
        metrics = self._get_or_create_metrics(endpoint_id)
        metrics.consecutive_failures += 1
        metrics.total_failures += 1
        metrics.last_failure_time = time.time()

        cooldown = self._compute_cooldown(
            metrics.consecutive_failures, metrics.learned_decay_factor
        )
        metrics.current_cooldown_ms = cooldown

        if metrics.consecutive_failures >= self._failure_threshold:
            old_state = self._circuit_states.get(endpoint_id, CircuitState.CLOSED)
            self._circuit_states[endpoint_id] = CircuitState.OPEN
            if old_state != CircuitState.OPEN:
                logger.warning(
                    "Circuit OPENED for %s | failures=%d | "
                    "cooldown=%.0fms | decay=%.2f",
                    endpoint_id,
                    metrics.consecutive_failures,
                    cooldown,
                    metrics.learned_decay_factor,
                )

        return cooldown

    def record_recovery_success(self, endpoint_id: str) -> None:
        """Record successful recovery — learn to recover faster."""
        metrics = self._get_or_create_metrics(endpoint_id)

        metrics.learned_decay_factor = max(
            self.MIN_DECAY_FACTOR,
            metrics.learned_decay_factor * (1.0 - self.SUCCESS_LEARNING_RATE),
        )
        metrics.total_recoveries += 1
        metrics.last_recovery_time = time.time()
        metrics.consecutive_failures = 0
        metrics.current_cooldown_ms = 0.0
        metrics.recovery_success_rate = (
            0.9 * metrics.recovery_success_rate + 0.1
        )

        self._circuit_states[endpoint_id] = CircuitState.CLOSED
        logger.info(
            "Circuit CLOSED for %s | recovery succeeded | "
            "decay=%.2f | success_rate=%.2f",
            endpoint_id,
            metrics.learned_decay_factor,
            metrics.recovery_success_rate,
        )

    def record_recovery_failure(self, endpoint_id: str) -> float:
        """Record failed recovery — learn to be more cautious."""
        metrics = self._get_or_create_metrics(endpoint_id)

        metrics.learned_decay_factor = min(
            self.MAX_DECAY_FACTOR,
            metrics.learned_decay_factor * (1.0 + self.FAILURE_LEARNING_RATE),
        )
        metrics.recovery_success_rate = (
            0.9 * metrics.recovery_success_rate
        )

        cooldown = self.record_failure(endpoint_id)
        self._circuit_states[endpoint_id] = CircuitState.OPEN

        logger.info(
            "Recovery FAILED for %s | back to OPEN | "
            "decay=%.2f | cooldown=%.0fms",
            endpoint_id,
            metrics.learned_decay_factor,
            cooldown,
        )
        return cooldown

    def should_attempt_recovery(self, endpoint_id: str) -> bool:
        """Check if cooldown elapsed and recovery should be probed."""
        state = self.get_circuit_state(endpoint_id)
        if state != CircuitState.OPEN:
            return False

        metrics = self._metrics.get(endpoint_id)
        if metrics is None:
            return False

        elapsed_ms = (time.time() - metrics.last_failure_time) * 1000.0
        if elapsed_ms >= metrics.current_cooldown_ms:
            self._circuit_states[endpoint_id] = CircuitState.HALF_OPEN
            logger.info(
                "Circuit HALF_OPEN for %s | cooldown %.0fms elapsed",
                endpoint_id,
                metrics.current_cooldown_ms,
            )
            return True

        return False

    def _compute_cooldown(self, failure_count: int, decay_factor: float) -> float:
        """Compute cooldown with exponential backoff and jitter."""
        raw = self._base_cooldown_ms * math.pow(decay_factor, failure_count - 1)
        jitter = 1.0 + random.uniform(-self._jitter_factor, self._jitter_factor)
        return min(raw * jitter, self._max_cooldown_ms)

    def _get_or_create_metrics(self, endpoint_id: str) -> CooldownMetrics:
        if endpoint_id not in self._metrics:
            self._metrics[endpoint_id] = CooldownMetrics(endpoint_id=endpoint_id)
        return self._metrics[endpoint_id]
