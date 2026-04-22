"""
Unit tests for RetryPolicy.

Tests: backoff strategies (exponential, linear, fibonacci, adaptive), error
classification by status code and exception type, retry decisions, jitter
behavior, and the maximum-cap.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import math
import random

from agentflow.resilience.retry_policy import (
    BackoffStrategy,
    ErrorClass,
    RetryPolicy,
)


def _no_jitter() -> RetryPolicy:
    return RetryPolicy(jitter=False)


class TestExponentialBackoff:
    def test_first_attempt_returns_base(self) -> None:
        p = RetryPolicy(strategy=BackoffStrategy.EXPONENTIAL, jitter=False)
        cfg = {"backoff_base": 1.0, "backoff_multiplier": 2.0}
        assert p.calculate_backoff(attempt=0, config=cfg) == 1.0

    def test_grows_geometrically(self) -> None:
        p = RetryPolicy(strategy=BackoffStrategy.EXPONENTIAL, jitter=False)
        cfg = {"backoff_base": 1.0, "backoff_multiplier": 2.0, "backoff_max": 1000.0}
        waits = [p.calculate_backoff(attempt=i, config=cfg) for i in range(5)]
        assert waits == [1.0, 2.0, 4.0, 8.0, 16.0]

    def test_respects_multiplier(self) -> None:
        p = RetryPolicy(strategy=BackoffStrategy.EXPONENTIAL, jitter=False)
        cfg = {"backoff_base": 2.0, "backoff_multiplier": 3.0, "backoff_max": 1000.0}
        assert p.calculate_backoff(attempt=2, config=cfg) == 2.0 * (3.0**2)


class TestLinearBackoff:
    def test_first_attempt(self) -> None:
        p = RetryPolicy(strategy=BackoffStrategy.LINEAR, jitter=False)
        assert p.calculate_backoff(attempt=0, config={"backoff_base": 1.5}) == 1.5

    def test_grows_linearly(self) -> None:
        p = RetryPolicy(strategy=BackoffStrategy.LINEAR, jitter=False)
        cfg = {"backoff_base": 2.0, "backoff_max": 1000.0}
        waits = [p.calculate_backoff(attempt=i, config=cfg) for i in range(4)]
        assert waits == [2.0, 4.0, 6.0, 8.0]


class TestFibonacciBackoff:
    def test_sequence(self) -> None:
        p = RetryPolicy(strategy=BackoffStrategy.FIBONACCI, jitter=False)
        cfg = {"backoff_base": 1.0, "backoff_max": 1000.0}
        # fib(2)=1, fib(3)=2, fib(4)=3, fib(5)=5, fib(6)=8
        waits = [p.calculate_backoff(attempt=i, config=cfg) for i in range(5)]
        assert waits == [1.0, 2.0, 3.0, 5.0, 8.0]

    def test_scaled_by_base(self) -> None:
        p = RetryPolicy(strategy=BackoffStrategy.FIBONACCI, jitter=False)
        cfg = {"backoff_base": 0.5, "backoff_max": 1000.0}
        assert p.calculate_backoff(attempt=4, config=cfg) == 0.5 * 8


class TestAdaptiveBackoff:
    def test_rate_limited_longer_than_transient(self) -> None:
        p = RetryPolicy(strategy=BackoffStrategy.ADAPTIVE, jitter=False)
        cfg = {"backoff_base": 1.0, "backoff_multiplier": 2.0, "backoff_max": 10_000.0}
        transient = p.calculate_backoff(attempt=2, config=cfg, error_class=ErrorClass.TRANSIENT)
        rate_limited = p.calculate_backoff(
            attempt=2, config=cfg, error_class=ErrorClass.RATE_LIMITED
        )
        assert rate_limited > transient

    def test_server_error_longer_than_transient(self) -> None:
        p = RetryPolicy(strategy=BackoffStrategy.ADAPTIVE, jitter=False)
        cfg = {"backoff_base": 1.0, "backoff_multiplier": 2.0, "backoff_max": 10_000.0}
        transient = p.calculate_backoff(attempt=2, config=cfg, error_class=ErrorClass.TRANSIENT)
        server = p.calculate_backoff(attempt=2, config=cfg, error_class=ErrorClass.SERVER_ERROR)
        assert server > transient

    def test_transient_matches_exponential(self) -> None:
        p_adapt = RetryPolicy(strategy=BackoffStrategy.ADAPTIVE, jitter=False)
        p_exp = RetryPolicy(strategy=BackoffStrategy.EXPONENTIAL, jitter=False)
        cfg = {"backoff_base": 1.0, "backoff_multiplier": 2.0, "backoff_max": 10_000.0}
        a = p_adapt.calculate_backoff(attempt=3, config=cfg, error_class=ErrorClass.TRANSIENT)
        b = p_exp.calculate_backoff(attempt=3, config=cfg)
        assert math.isclose(a, b)


class TestMaxCap:
    def test_exponential_capped(self) -> None:
        p = RetryPolicy(strategy=BackoffStrategy.EXPONENTIAL, jitter=False)
        cfg = {"backoff_base": 1.0, "backoff_multiplier": 2.0, "backoff_max": 5.0}
        assert p.calculate_backoff(attempt=10, config=cfg) == 5.0

    def test_fibonacci_capped(self) -> None:
        p = RetryPolicy(strategy=BackoffStrategy.FIBONACCI, jitter=False)
        cfg = {"backoff_base": 1.0, "backoff_max": 10.0}
        assert p.calculate_backoff(attempt=20, config=cfg) == 10.0

    def test_default_config_has_60s_cap(self) -> None:
        p = RetryPolicy(strategy=BackoffStrategy.EXPONENTIAL, jitter=False)
        # attempt=20 with multiplier 2 would be ~1M sec; cap should clamp to 60.
        assert p.calculate_backoff(attempt=20) == 60.0


class TestJitter:
    def test_jitter_produces_variation(self) -> None:
        random.seed(0)
        p = RetryPolicy(strategy=BackoffStrategy.EXPONENTIAL, jitter=True, jitter_range=0.5)
        cfg = {"backoff_base": 10.0, "backoff_multiplier": 2.0, "backoff_max": 1000.0}
        waits = {round(p.calculate_backoff(attempt=2, config=cfg), 4) for _ in range(20)}
        assert len(waits) > 1

    def test_jitter_within_range(self) -> None:
        random.seed(42)
        base_value = 10.0
        p = RetryPolicy(
            strategy=BackoffStrategy.EXPONENTIAL, jitter=True, jitter_range=0.25
        )
        cfg = {"backoff_base": base_value, "backoff_multiplier": 1.0, "backoff_max": 1000.0}
        for _ in range(50):
            wait = p.calculate_backoff(attempt=0, config=cfg)
            # base*1^0 = 10, +/- 25% = [7.5, 12.5]
            assert 7.5 - 1e-6 <= wait <= 12.5 + 1e-6

    def test_jitter_never_negative(self) -> None:
        random.seed(123)
        p = RetryPolicy(strategy=BackoffStrategy.EXPONENTIAL, jitter=True, jitter_range=2.0)
        cfg = {"backoff_base": 0.1, "backoff_multiplier": 1.0, "backoff_max": 1000.0}
        for _ in range(100):
            assert p.calculate_backoff(attempt=0, config=cfg) >= 0.0


class TestErrorClassification:
    def test_429_is_rate_limited(self) -> None:
        assert RetryPolicy().classify_error(status_code=429) == ErrorClass.RATE_LIMITED

    def test_503_504_are_transient(self) -> None:
        p = RetryPolicy()
        assert p.classify_error(status_code=503) == ErrorClass.TRANSIENT
        assert p.classify_error(status_code=504) == ErrorClass.TRANSIENT

    def test_500_502_are_server_error(self) -> None:
        p = RetryPolicy()
        assert p.classify_error(status_code=500) == ErrorClass.SERVER_ERROR
        assert p.classify_error(status_code=502) == ErrorClass.SERVER_ERROR

    def test_4xx_excluding_429_is_client_error(self) -> None:
        p = RetryPolicy()
        for code in (400, 401, 403, 404, 422):
            assert p.classify_error(status_code=code) == ErrorClass.CLIENT_ERROR

    def test_timeout_exception_is_transient(self) -> None:
        assert RetryPolicy().classify_error(error=TimeoutError("slow")) == ErrorClass.TRANSIENT

    def test_connection_error_is_transient(self) -> None:
        assert (
            RetryPolicy().classify_error(error=ConnectionError("refused"))
            == ErrorClass.TRANSIENT
        )

    def test_unknown_returns_unknown(self) -> None:
        assert RetryPolicy().classify_error() == ErrorClass.UNKNOWN
        assert RetryPolicy().classify_error(error=ValueError("x")) == ErrorClass.UNKNOWN


class TestShouldRetry:
    def test_retries_transient(self) -> None:
        assert RetryPolicy().should_retry(ErrorClass.TRANSIENT) is True

    def test_retries_rate_limited(self) -> None:
        assert RetryPolicy().should_retry(ErrorClass.RATE_LIMITED) is True

    def test_retries_server_error(self) -> None:
        assert RetryPolicy().should_retry(ErrorClass.SERVER_ERROR) is True

    def test_does_not_retry_client_error(self) -> None:
        assert RetryPolicy().should_retry(ErrorClass.CLIENT_ERROR) is False

    def test_does_not_retry_unknown(self) -> None:
        assert RetryPolicy().should_retry(ErrorClass.UNKNOWN) is False


class TestDefaults:
    def test_default_strategy_is_exponential(self) -> None:
        assert RetryPolicy().strategy == BackoffStrategy.EXPONENTIAL

    def test_jitter_enabled_by_default(self) -> None:
        assert RetryPolicy().jitter is True

    def test_default_jitter_range(self) -> None:
        assert RetryPolicy().jitter_range == 0.25

    def test_calculate_backoff_with_no_config(self) -> None:
        p = _no_jitter()
        # base=1.0, multiplier=2.0 by default
        assert p.calculate_backoff(attempt=3) == 8.0

    def test_returns_float(self) -> None:
        p = _no_jitter()
        result = p.calculate_backoff(attempt=1)
        assert isinstance(result, float)
