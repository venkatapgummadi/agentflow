"""
Unit tests for ``agentflow.resilience.retry_policy.RetryPolicy``.

Covers:
- Exponential, linear, fibonacci, and adaptive backoff strategies
- Error classification (TRANSIENT / RATE_LIMITED / SERVER_ERROR /
  CLIENT_ERROR / UNKNOWN)
- ``should_retry`` decision logic per ErrorClass
- Jitter bounds (deterministic via fixed-seed RNG)
- Backoff cap (``backoff_max``)
- Default config fallthrough

These tests close the long-standing TODO from CHANGELOG.md ("Unit tests
for ``RetryPolicy`` are still missing") and bring the resilience layer
to parity with circuit-breaker and bulkhead test coverage.
"""
from __future__ import annotations

import random

import pytest
from agentflow.resilience.retry_policy import (
    BackoffStrategy,
    ErrorClass,
    RetryPolicy,
)

# ---------------------------------------------------------------------------
# Backoff strategies
# ---------------------------------------------------------------------------


class TestExponentialBackoff:
    """Exponential strategy: wait = base * multiplier^attempt."""

    def setup_method(self) -> None:
        self.policy = RetryPolicy(
            strategy=BackoffStrategy.EXPONENTIAL, jitter=False
        )

    def test_attempt_zero_returns_base(self) -> None:
        wait = self.policy.calculate_backoff(
            attempt=0, config={"backoff_base": 1.0, "backoff_multiplier": 2.0}
        )
        assert wait == pytest.approx(1.0)

    def test_attempt_one_doubles(self) -> None:
        wait = self.policy.calculate_backoff(
            attempt=1, config={"backoff_base": 1.0, "backoff_multiplier": 2.0}
        )
        assert wait == pytest.approx(2.0)

    def test_attempt_three_is_eight(self) -> None:
        wait = self.policy.calculate_backoff(
            attempt=3, config={"backoff_base": 1.0, "backoff_multiplier": 2.0}
        )
        assert wait == pytest.approx(8.0)

    def test_custom_multiplier(self) -> None:
        wait = self.policy.calculate_backoff(
            attempt=2, config={"backoff_base": 0.5, "backoff_multiplier": 3.0}
        )
        # 0.5 * 3^2 = 4.5
        assert wait == pytest.approx(4.5)


class TestLinearBackoff:
    """Linear strategy: wait = base * (attempt + 1)."""

    def setup_method(self) -> None:
        self.policy = RetryPolicy(strategy=BackoffStrategy.LINEAR, jitter=False)

    def test_attempt_zero(self) -> None:
        wait = self.policy.calculate_backoff(
            attempt=0, config={"backoff_base": 2.0}
        )
        assert wait == pytest.approx(2.0)

    def test_attempt_three(self) -> None:
        wait = self.policy.calculate_backoff(
            attempt=3, config={"backoff_base": 2.0}
        )
        # 2 * (3+1) = 8
        assert wait == pytest.approx(8.0)


class TestFibonacciBackoff:
    """Fibonacci strategy: wait = base * fib(attempt + 2)."""

    def setup_method(self) -> None:
        self.policy = RetryPolicy(
            strategy=BackoffStrategy.FIBONACCI, jitter=False
        )

    def test_attempt_zero_is_one(self) -> None:
        # The implementation returns base*b after 0 iterations of the fib
        # loop, where b starts at 1 → fib(2) == 1.
        wait = self.policy.calculate_backoff(
            attempt=0, config={"backoff_base": 1.0}
        )
        assert wait == pytest.approx(1.0)

    def test_first_few_terms(self) -> None:
        # Expected fib sequence under this implementation:
        # attempt 0 → 1, 1 → 2, 2 → 3, 3 → 5, 4 → 8, 5 → 13.
        expected = [1, 2, 3, 5, 8, 13]
        for attempt, want in enumerate(expected):
            wait = self.policy.calculate_backoff(
                attempt=attempt, config={"backoff_base": 1.0}
            )
            assert wait == pytest.approx(float(want)), f"attempt={attempt}"

    def test_scales_with_base(self) -> None:
        wait = self.policy.calculate_backoff(
            attempt=4, config={"backoff_base": 0.5}
        )
        # 0.5 * 8 = 4.0
        assert wait == pytest.approx(4.0)


class TestAdaptiveBackoff:
    """Adaptive strategy modulates by ErrorClass."""

    def setup_method(self) -> None:
        self.policy = RetryPolicy(
            strategy=BackoffStrategy.ADAPTIVE, jitter=False
        )
        self.cfg = {
            "backoff_base": 1.0,
            "backoff_multiplier": 2.0,
            "backoff_max": 1000.0,
        }

    def test_rate_limited_multiplies_attempt_plus_one_by_two(self) -> None:
        # base * mult^(attempt+1) * 2 = 1 * 2^(2+1) * 2 = 16
        wait = self.policy.calculate_backoff(
            attempt=2, config=self.cfg, error_class=ErrorClass.RATE_LIMITED
        )
        assert wait == pytest.approx(16.0)

    def test_server_error_uses_1_5_multiplier(self) -> None:
        # 1 * 2^2 * 1.5 = 6
        wait = self.policy.calculate_backoff(
            attempt=2, config=self.cfg, error_class=ErrorClass.SERVER_ERROR
        )
        assert wait == pytest.approx(6.0)

    def test_transient_falls_back_to_exponential(self) -> None:
        # 1 * 2^2 = 4
        wait = self.policy.calculate_backoff(
            attempt=2, config=self.cfg, error_class=ErrorClass.TRANSIENT
        )
        assert wait == pytest.approx(4.0)

    def test_unknown_falls_back_to_exponential(self) -> None:
        wait = self.policy.calculate_backoff(
            attempt=2, config=self.cfg, error_class=ErrorClass.UNKNOWN
        )
        assert wait == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


class TestClassifyError:
    """Status-code → ErrorClass mapping."""

    def setup_method(self) -> None:
        self.policy = RetryPolicy()

    def test_429_is_rate_limited(self) -> None:
        assert (
            self.policy.classify_error(status_code=429)
            == ErrorClass.RATE_LIMITED
        )

    def test_503_is_transient(self) -> None:
        assert (
            self.policy.classify_error(status_code=503) == ErrorClass.TRANSIENT
        )

    def test_504_is_transient(self) -> None:
        assert (
            self.policy.classify_error(status_code=504) == ErrorClass.TRANSIENT
        )

    def test_500_is_server_error(self) -> None:
        assert (
            self.policy.classify_error(status_code=500)
            == ErrorClass.SERVER_ERROR
        )

    def test_502_is_server_error(self) -> None:
        assert (
            self.policy.classify_error(status_code=502)
            == ErrorClass.SERVER_ERROR
        )

    @pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
    def test_4xx_other_than_429_is_client_error(self, code: int) -> None:
        assert (
            self.policy.classify_error(status_code=code)
            == ErrorClass.CLIENT_ERROR
        )

    def test_timeout_exception_is_transient(self) -> None:
        assert (
            self.policy.classify_error(error=TimeoutError("slow"))
            == ErrorClass.TRANSIENT
        )

    def test_connection_error_is_transient(self) -> None:
        assert (
            self.policy.classify_error(error=ConnectionError("rst"))
            == ErrorClass.TRANSIENT
        )

    def test_unknown_exception_falls_through(self) -> None:
        assert (
            self.policy.classify_error(error=ValueError("oops"))
            == ErrorClass.UNKNOWN
        )

    def test_no_information_is_unknown(self) -> None:
        assert self.policy.classify_error() == ErrorClass.UNKNOWN


# ---------------------------------------------------------------------------
# Retry decision
# ---------------------------------------------------------------------------


class TestShouldRetry:
    """Retry decision based on ErrorClass."""

    def setup_method(self) -> None:
        self.policy = RetryPolicy()

    @pytest.mark.parametrize(
        "ec",
        [
            ErrorClass.TRANSIENT,
            ErrorClass.RATE_LIMITED,
            ErrorClass.SERVER_ERROR,
        ],
    )
    def test_retry_yes(self, ec: ErrorClass) -> None:
        assert self.policy.should_retry(ec) is True

    @pytest.mark.parametrize(
        "ec",
        [
            ErrorClass.CLIENT_ERROR,
            ErrorClass.UNKNOWN,
        ],
    )
    def test_retry_no(self, ec: ErrorClass) -> None:
        assert self.policy.should_retry(ec) is False


# ---------------------------------------------------------------------------
# Backoff cap and jitter
# ---------------------------------------------------------------------------


class TestBackoffCap:
    """``backoff_max`` is enforced."""

    def setup_method(self) -> None:
        self.policy = RetryPolicy(
            strategy=BackoffStrategy.EXPONENTIAL, jitter=False
        )

    def test_capped_at_maximum(self) -> None:
        # 1 * 2^10 = 1024 → capped to 60
        wait = self.policy.calculate_backoff(
            attempt=10,
            config={
                "backoff_base": 1.0,
                "backoff_multiplier": 2.0,
                "backoff_max": 60.0,
            },
        )
        assert wait == pytest.approx(60.0)

    def test_default_cap_is_sixty(self) -> None:
        wait = self.policy.calculate_backoff(attempt=20, config={})
        assert wait == pytest.approx(60.0)


class TestJitter:
    """Jitter stays within ``[wait*(1-r), wait*(1+r)]`` and is non-negative."""

    def test_jitter_within_bounds(self) -> None:
        random.seed(0xA9F3)
        policy = RetryPolicy(
            strategy=BackoffStrategy.LINEAR, jitter=True, jitter_range=0.25
        )
        # base wait = 4 * (3+1) = 16
        for _ in range(200):
            wait = policy.calculate_backoff(
                attempt=3, config={"backoff_base": 4.0}
            )
            assert 12.0 <= wait <= 20.0

    def test_jitter_never_negative(self) -> None:
        # Even with very large jitter_range, the implementation clips to 0.
        random.seed(7)
        policy = RetryPolicy(
            strategy=BackoffStrategy.LINEAR, jitter=True, jitter_range=2.0
        )
        for _ in range(200):
            wait = policy.calculate_backoff(
                attempt=0, config={"backoff_base": 1.0}
            )
            assert wait >= 0.0

    def test_jitter_disabled_is_deterministic(self) -> None:
        policy = RetryPolicy(
            strategy=BackoffStrategy.EXPONENTIAL, jitter=False
        )
        cfg = {"backoff_base": 1.0, "backoff_multiplier": 2.0}
        runs = {policy.calculate_backoff(attempt=4, config=cfg) for _ in range(20)}
        assert len(runs) == 1
        assert next(iter(runs)) == pytest.approx(16.0)


# ---------------------------------------------------------------------------
# Defaults / config fallthrough
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_no_config_uses_default_base(self) -> None:
        policy = RetryPolicy(
            strategy=BackoffStrategy.EXPONENTIAL, jitter=False
        )
        # base=1, multiplier=2, attempt=2 → 4
        wait = policy.calculate_backoff(attempt=2, config=None)
        assert wait == pytest.approx(4.0)

    def test_returns_float(self) -> None:
        policy = RetryPolicy(jitter=False)
        wait = policy.calculate_backoff(attempt=1)
        assert isinstance(wait, float)
