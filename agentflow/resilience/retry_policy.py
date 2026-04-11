"""
Retry Policy — adaptive retry strategies for transient failures.

Supports multiple backoff algorithms:
- Exponential backoff with jitter
- Linear backoff
- Fibonacci backoff
- Adaptive backoff based on error classification

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import logging
import random
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BackoffStrategy(Enum):
    """Available backoff algorithms."""

    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIBONACCI = "fibonacci"
    ADAPTIVE = "adaptive"


class ErrorClass(Enum):
    """Error classification for adaptive retry."""

    TRANSIENT = "transient"          # Network timeout, 503
    RATE_LIMITED = "rate_limited"    # 429 Too Many Requests
    SERVER_ERROR = "server_error"    # 500, 502, 504
    CLIENT_ERROR = "client_error"   # 400, 401, 403 (not retryable)
    UNKNOWN = "unknown"


class RetryPolicy:
    """
    Configurable retry policy with multiple backoff strategies.

    The policy calculates the appropriate wait time between retries
    based on the chosen backoff strategy and error classification.

    Usage:
        policy = RetryPolicy(strategy=BackoffStrategy.EXPONENTIAL)
        wait = policy.calculate_backoff(attempt=2, config={"backoff_base": 1.0})
        await asyncio.sleep(wait)
    """

    def __init__(
        self,
        strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL,
        jitter: bool = True,
        jitter_range: float = 0.25,
    ):
        self.strategy = strategy
        self.jitter = jitter
        self.jitter_range = jitter_range

    def calculate_backoff(
        self,
        attempt: int,
        config: Optional[Dict[str, Any]] = None,
        error_class: ErrorClass = ErrorClass.TRANSIENT,
    ) -> float:
        """
        Calculate the backoff duration for a given attempt.

        Args:
            attempt: Zero-based attempt number.
            config: Retry configuration with base/max/multiplier.
            error_class: Classification of the error for adaptive backoff.

        Returns:
            Wait time in seconds before the next retry.
        """
        cfg = config or {}
        base = cfg.get("backoff_base", 1.0)
        maximum = cfg.get("backoff_max", 60.0)
        multiplier = cfg.get("backoff_multiplier", 2.0)

        if self.strategy == BackoffStrategy.EXPONENTIAL:
            wait = self._exponential(attempt, base, multiplier)
        elif self.strategy == BackoffStrategy.LINEAR:
            wait = self._linear(attempt, base)
        elif self.strategy == BackoffStrategy.FIBONACCI:
            wait = self._fibonacci(attempt, base)
        elif self.strategy == BackoffStrategy.ADAPTIVE:
            wait = self._adaptive(attempt, base, multiplier, error_class)
        else:
            wait = base

        # Cap at maximum
        wait = min(wait, maximum)

        # Apply jitter to prevent thundering herd
        if self.jitter:
            jitter_amount = wait * self.jitter_range
            wait += random.uniform(-jitter_amount, jitter_amount)
            wait = max(0.0, wait)

        return wait

    def classify_error(
        self, status_code: int = 0, error: Optional[Exception] = None
    ) -> ErrorClass:
        """Classify an error for adaptive retry behavior."""
        if status_code == 429:
            return ErrorClass.RATE_LIMITED
        elif status_code in (503, 504):
            return ErrorClass.TRANSIENT
        elif 500 <= status_code < 600:
            return ErrorClass.SERVER_ERROR
        elif 400 <= status_code < 500:
            return ErrorClass.CLIENT_ERROR
        elif error and isinstance(error, (TimeoutError, ConnectionError)):
            return ErrorClass.TRANSIENT
        return ErrorClass.UNKNOWN

    def should_retry(self, error_class: ErrorClass) -> bool:
        """Determine if a retry is appropriate for this error class."""
        return error_class in (
            ErrorClass.TRANSIENT,
            ErrorClass.RATE_LIMITED,
            ErrorClass.SERVER_ERROR,
        )

    # ── Backoff Algorithms ────────────────────────────────────────────

    @staticmethod
    def _exponential(attempt: int, base: float, multiplier: float) -> float:
        """Exponential backoff: base * multiplier^attempt."""
        return base * (multiplier ** attempt)

    @staticmethod
    def _linear(attempt: int, base: float) -> float:
        """Linear backoff: base * (attempt + 1)."""
        return base * (attempt + 1)

    @staticmethod
    def _fibonacci(attempt: int, base: float) -> float:
        """Fibonacci backoff: base * fib(attempt + 2)."""
        a, b = 1, 1
        for _ in range(attempt):
            a, b = b, a + b
        return base * b

    @staticmethod
    def _adaptive(
        attempt: int,
        base: float,
        multiplier: float,
        error_class: ErrorClass,
    ) -> float:
        """
        Adaptive backoff based on error classification.

        - Rate limited: longer waits (respect server backpressure)
        - Transient: standard exponential
        - Server error: moderate backoff
        """
        if error_class == ErrorClass.RATE_LIMITED:
            # Respect rate limits with longer waits
            return base * (multiplier ** (attempt + 1)) * 2
        elif error_class == ErrorClass.SERVER_ERROR:
            return base * (multiplier ** attempt) * 1.5
        else:
            return base * (multiplier ** attempt)
