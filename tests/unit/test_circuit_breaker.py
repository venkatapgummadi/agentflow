"""
Tests for the CircuitBreaker resilience pattern.

Verifies state transitions, adaptive cooldown, and failure threshold behavior.

Author: Venkata Pavan Kumar Gummadi
"""

import time
import pytest
from agentflow.resilience.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreakerBasic:
    """Test basic circuit breaker operations."""

    def test_initial_state_is_closed(self):
        cb = CircuitBreaker(name="test")
        assert cb.state == CircuitState.CLOSED

    def test_allows_requests_when_closed(self):
        cb = CircuitBreaker(name="test")
        assert cb.allow_request() is True

    def test_records_success(self):
        cb = CircuitBreaker(name="test")
        cb.record_success()
        metrics = cb.get_metrics()
        assert metrics["total_requests"] == 1
        assert metrics["total_failures"] == 0

    def test_records_failure(self):
        cb = CircuitBreaker(name="test")
        cb.record_failure()
        metrics = cb.get_metrics()
        assert metrics["total_requests"] == 1
        assert metrics["total_failures"] == 1


class TestCircuitBreakerTransitions:
    """Test circuit state transitions."""

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(name="test", failure_threshold=3, window_seconds=60)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_blocks_requests_when_open(self):
        cb = CircuitBreaker(name="test", failure_threshold=2, window_seconds=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.allow_request() is False

    def test_transitions_to_half_open_after_cooldown(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=1,
            cooldown_seconds=0.01,
            window_seconds=60,
        )
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_after_success_in_half_open(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=1,
            success_threshold=1,
            cooldown_seconds=0.01,
            window_seconds=60,
        )
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reopens_on_failure_in_half_open(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=1,
            cooldown_seconds=0.01,
            window_seconds=60,
        )
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerAdaptive:
    """Test adaptive cooldown behavior."""

    def test_cooldown_increases_with_consecutive_opens(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=1,
            cooldown_seconds=1.0,
            max_cooldown_seconds=100.0,
            window_seconds=60,
        )
        # First open
        cb.record_failure()
        assert cb._current_cooldown == 2.0  # 1.0 * 2^1

    def test_force_open(self):
        cb = CircuitBreaker(name="test")
        cb.force_open()
        assert cb.state == CircuitState.OPEN

    def test_force_close(self):
        cb = CircuitBreaker(name="test")
        cb.force_open()
        cb.force_close()
        assert cb.state == CircuitState.CLOSED

    def test_failure_rate_calculation(self):
        cb = CircuitBreaker(name="test", failure_threshold=10, window_seconds=60)
        cb.record_success()
        cb.record_success()
        cb.record_failure()
        assert abs(cb.failure_rate - 1 / 3) < 0.01
