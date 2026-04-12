"""
Unit tests for ExponentialCooldownStrategy.

Tests: circuit state transitions, exponential backoff, cooldown learning,
decay factor bounds, jitter, multi-endpoint independence.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import time

import pytest

from agentflow.resilience.circuit_breaker import CircuitState
from agentflow.resilience.cooldown_strategy import (
    CooldownMetrics,
    ExponentialCooldownStrategy,
)


class TestCircuitStateTransitions:
    def test_initial_state_closed(self) -> None:
        s = ExponentialCooldownStrategy()
        assert s.get_circuit_state("api") == CircuitState.CLOSED

    def test_opens_after_threshold(self) -> None:
        s = ExponentialCooldownStrategy(failure_threshold=3)
        for _ in range(3):
            s.record_failure("api")
        assert s.get_circuit_state("api") == CircuitState.OPEN

    def test_stays_closed_below_threshold(self) -> None:
        s = ExponentialCooldownStrategy(failure_threshold=3)
        s.record_failure("api")
        s.record_failure("api")
        assert s.get_circuit_state("api") == CircuitState.CLOSED

    def test_half_open_after_cooldown(self) -> None:
        s = ExponentialCooldownStrategy(base_cooldown_ms=100, failure_threshold=1)
        s.record_failure("api")
        s._metrics["api"].last_failure_time = time.time() - 1.0
        assert s.should_attempt_recovery("api") is True
        assert s.get_circuit_state("api") == CircuitState.HALF_OPEN

    def test_closes_on_success(self) -> None:
        s = ExponentialCooldownStrategy(failure_threshold=1)
        s.record_failure("api")
        s.record_recovery_success("api")
        assert s.get_circuit_state("api") == CircuitState.CLOSED

    def test_reopens_on_failed_recovery(self) -> None:
        s = ExponentialCooldownStrategy(failure_threshold=1)
        s.record_failure("api")
        s.record_recovery_failure("api")
        assert s.get_circuit_state("api") == CircuitState.OPEN


class TestCooldownComputation:
    def test_first_failure_base_cooldown(self) -> None:
        s = ExponentialCooldownStrategy(base_cooldown_ms=1000, jitter_factor=0.0)
        cd = s.record_failure("api")
        assert abs(cd - 1000.0) < 1.0

    def test_cooldown_increases(self) -> None:
        s = ExponentialCooldownStrategy(
            base_cooldown_ms=1000, jitter_factor=0.0, failure_threshold=999
        )
        cooldowns = [s.record_failure("api") for _ in range(4)]
        for i in range(1, len(cooldowns)):
            assert cooldowns[i] > cooldowns[i - 1]

    def test_cooldown_capped(self) -> None:
        s = ExponentialCooldownStrategy(
            base_cooldown_ms=1000, max_cooldown_ms=5000,
            jitter_factor=0.0, failure_threshold=999,
        )
        for _ in range(20):
            cd = s.record_failure("api")
        assert cd <= 5000.0

    def test_jitter_creates_variation(self) -> None:
        s = ExponentialCooldownStrategy(base_cooldown_ms=1000, jitter_factor=0.2)
        cooldowns = set()
        for i in range(20):
            s._metrics.clear()
            s._circuit_states.clear()
            cooldowns.add(round(s.record_failure(f"api-{i}"), 2))
        assert len(cooldowns) > 1


class TestCooldownLearning:
    def test_success_reduces_decay(self) -> None:
        s = ExponentialCooldownStrategy(failure_threshold=1)
        s.record_failure("api")
        before = s._metrics["api"].learned_decay_factor
        s.record_recovery_success("api")
        assert s._metrics["api"].learned_decay_factor < before

    def test_failure_increases_decay(self) -> None:
        s = ExponentialCooldownStrategy(failure_threshold=1)
        s.record_failure("api")
        before = s._metrics["api"].learned_decay_factor
        s.record_recovery_failure("api")
        assert s._metrics["api"].learned_decay_factor > before

    def test_decay_bounded_min(self) -> None:
        s = ExponentialCooldownStrategy(failure_threshold=1)
        for _ in range(100):
            s.record_failure("api")
            s.record_recovery_success("api")
        assert s._metrics["api"].learned_decay_factor >= s.MIN_DECAY_FACTOR

    def test_decay_bounded_max(self) -> None:
        s = ExponentialCooldownStrategy(failure_threshold=1)
        for _ in range(100):
            s.record_failure("api")
            s.record_recovery_failure("api")
        assert s._metrics["api"].learned_decay_factor <= s.MAX_DECAY_FACTOR


class TestMultiEndpoint:
    def test_independent_states(self) -> None:
        s = ExponentialCooldownStrategy(failure_threshold=2)
        s.record_failure("api-1")
        s.record_failure("api-1")
        s.record_failure("api-2")
        assert s.get_circuit_state("api-1") == CircuitState.OPEN
        assert s.get_circuit_state("api-2") == CircuitState.CLOSED

    def test_independent_learning(self) -> None:
        s = ExponentialCooldownStrategy(failure_threshold=1)
        s.record_failure("api-1")
        s.record_recovery_success("api-1")
        s.record_failure("api-2")
        s.record_recovery_failure("api-2")
        assert s._metrics["api-1"].learned_decay_factor < s._metrics["api-2"].learned_decay_factor


class TestMetrics:
    def test_failure_count(self) -> None:
        s = ExponentialCooldownStrategy()
        s.record_failure("api")
        s.record_failure("api")
        m = s.get_metrics("api")
        assert m is not None
        assert m.consecutive_failures == 2

    def test_recovery_resets_consecutive(self) -> None:
        s = ExponentialCooldownStrategy(failure_threshold=1)
        s.record_failure("api")
        s.record_recovery_success("api")
        m = s.get_metrics("api")
        assert m.consecutive_failures == 0
        assert m.total_recoveries == 1

    def test_metrics_serialization(self) -> None:
        s = ExponentialCooldownStrategy(failure_threshold=1)
        s.record_failure("api")
        d = s.get_metrics("api").to_dict()
        assert d["endpoint_id"] == "api"
        assert "learned_decay_factor" in d

    def test_unknown_endpoint_returns_none(self) -> None:
        s = ExponentialCooldownStrategy()
        assert s.get_metrics("nonexistent") is None

    def test_get_all_metrics(self) -> None:
        s = ExponentialCooldownStrategy()
        s.record_failure("api-1")
        s.record_failure("api-2")
        all_m = s.get_all_metrics()
        assert len(all_m) == 2
