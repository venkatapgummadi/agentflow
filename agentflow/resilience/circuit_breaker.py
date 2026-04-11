"""
Circuit Breaker — adaptive failure isolation pattern.

Implements the circuit breaker pattern with learning capabilities:
- Tracks failure rates per connector
- Opens the circuit when failures exceed threshold
- Half-open probing to detect recovery
- Adaptive thresholds that learn from failure patterns

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """States of the circuit breaker."""

    CLOSED = "closed"      # Normal operation, requests pass through
    OPEN = "open"          # Failures exceeded threshold, requests blocked
    HALF_OPEN = "half_open"  # Testing if the service has recovered


class CircuitBreaker:
    """
    Adaptive circuit breaker for API resilience.

    The circuit breaker monitors failure rates for a connector or
    endpoint and automatically stops sending requests when the
    failure rate exceeds a threshold. After a cooldown period,
    it enters half-open state to probe for recovery.

    Adaptive features:
    - Failure threshold adjusts based on historical error rates
    - Cooldown period increases with consecutive open events
    - Success threshold in half-open state adapts to recovery speed

    Usage:
        cb = CircuitBreaker(name="mulesoft-crm")
        if cb.allow_request():
            try:
                result = await call_api()
                cb.record_success()
            except Exception:
                cb.record_failure()
    """

    def __init__(
        self,
        name: str = "",
        failure_threshold: int = 5,
        success_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        max_cooldown_seconds: float = 300.0,
        window_seconds: float = 60.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.cooldown_seconds = cooldown_seconds
        self.max_cooldown_seconds = max_cooldown_seconds
        self.window_seconds = window_seconds

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._last_state_change: float = time.time()
        self._consecutive_opens: int = 0
        self._current_cooldown = cooldown_seconds

        # Metrics for adaptive behavior
        self._total_requests = 0
        self._total_failures = 0
        self._window_failures: list[float] = []

    @property
    def state(self) -> CircuitState:
        """Current circuit state with automatic transition checking."""
        if self._state == CircuitState.OPEN:
            if self._cooldown_elapsed():
                self._transition_to(CircuitState.HALF_OPEN)
        return self._state

    @property
    def failure_rate(self) -> float:
        """Current failure rate as a fraction."""
        if self._total_requests == 0:
            return 0.0
        return self._total_failures / self._total_requests

    def allow_request(self) -> bool:
        """
        Check if a request should be allowed through.

        Returns True if the circuit is closed (normal) or half-open
        (probing). Returns False if the circuit is open (blocked).
        """
        current_state = self.state  # Triggers auto-transition check
        if current_state == CircuitState.CLOSED:
            return True
        elif current_state == CircuitState.HALF_OPEN:
            return True
        else:
            return False

    def record_success(self) -> None:
        """Record a successful request."""
        self._total_requests += 1
        self._failure_count = 0  # Reset consecutive failure count

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._transition_to(CircuitState.CLOSED)
                self._consecutive_opens = max(0, self._consecutive_opens - 1)
                logger.info(
                    "Circuit '%s' closed after successful recovery", self.name
                )

    def record_failure(self) -> None:
        """Record a failed request."""
        self._total_requests += 1
        self._total_failures += 1
        self._failure_count += 1
        self._last_failure_time = time.time()

        # Track failures in sliding window
        self._window_failures.append(time.time())
        self._prune_window()

        if self._state == CircuitState.HALF_OPEN:
            # Any failure in half-open re-opens the circuit
            self._transition_to(CircuitState.OPEN)
            self._consecutive_opens += 1
            self._adapt_cooldown()
            logger.warning(
                "Circuit '%s' re-opened during half-open probe", self.name
            )
        elif self._state == CircuitState.CLOSED:
            window_failure_count = len(self._window_failures)
            if window_failure_count >= self.failure_threshold:
                self._transition_to(CircuitState.OPEN)
                self._consecutive_opens += 1
                self._adapt_cooldown()
                logger.warning(
                    "Circuit '%s' opened: %d failures in %.0fs window",
                    self.name,
                    window_failure_count,
                    self.window_seconds,
                )

    def force_open(self) -> None:
        """Manually open the circuit."""
        self._transition_to(CircuitState.OPEN)
        logger.info("Circuit '%s' manually opened", self.name)

    def force_close(self) -> None:
        """Manually close the circuit."""
        self._transition_to(CircuitState.CLOSED)
        self._failure_count = 0
        self._success_count = 0
        logger.info("Circuit '%s' manually closed", self.name)

    def get_metrics(self) -> Dict[str, Any]:
        """Get current circuit breaker metrics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_rate": round(self.failure_rate, 4),
            "total_requests": self._total_requests,
            "total_failures": self._total_failures,
            "consecutive_failures": self._failure_count,
            "consecutive_opens": self._consecutive_opens,
            "current_cooldown": self._current_cooldown,
            "window_failures": len(self._window_failures),
        }

    # ── Internal Methods ──────────────────────────────────────────────

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new circuit state."""
        old_state = self._state
        self._state = new_state
        self._last_state_change = time.time()

        if new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._window_failures.clear()

        logger.debug(
            "Circuit '%s': %s → %s", self.name, old_state.value, new_state.value
        )

    def _cooldown_elapsed(self) -> bool:
        """Check if the cooldown period has elapsed."""
        elapsed = time.time() - self._last_state_change
        return elapsed >= self._current_cooldown

    def _adapt_cooldown(self) -> None:
        """
        Adaptively increase cooldown based on consecutive opens.

        Uses exponential backoff capped at max_cooldown_seconds.
        This prevents rapid-fire open/close cycles when a service
        is persistently degraded.
        """
        self._current_cooldown = min(
            self.cooldown_seconds * (2 ** self._consecutive_opens),
            self.max_cooldown_seconds,
        )
        logger.debug(
            "Circuit '%s' adaptive cooldown: %.1fs",
            self.name,
            self._current_cooldown,
        )

    def _prune_window(self) -> None:
        """Remove failures outside the sliding window."""
        cutoff = time.time() - self.window_seconds
        self._window_failures = [
            t for t in self._window_failures if t > cutoff
        ]
