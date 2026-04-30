"""
Bulkhead — concurrency isolation pattern.

Limits the number of concurrent in-flight requests per connector
(or arbitrary key) to prevent one slow upstream from exhausting
shared resources (threads, sockets, memory).

Pairs naturally with CircuitBreaker and RetryPolicy:
- Bulkhead caps concurrency
- CircuitBreaker blocks on persistent failure
- RetryPolicy schedules transient retries

Usage:
    bulkhead = Bulkhead(name="mulesoft-crm", max_concurrent=10)
    async with bulkhead.acquire():
        result = await call_api()

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)


class BulkheadFullError(Exception):
    """Raised when the bulkhead has no capacity within the wait timeout."""


class Bulkhead:
    """
    Bounded-concurrency bulkhead with optional wait-queue limit.

    Args:
        name: Identifier (typically the connector or endpoint name).
        max_concurrent: Maximum simultaneous in-flight requests.
        max_queued: Maximum waiters allowed (raises BulkheadFullError
            once exceeded). Set 0 to disable queueing entirely.
        acquire_timeout: Default seconds to wait for a slot.
    """

    def __init__(
        self,
        name: str = "",
        max_concurrent: int = 10,
        max_queued: int = 50,
        acquire_timeout: float = 5.0,
    ):
        if max_concurrent <= 0:
            raise ValueError("max_concurrent must be > 0")
        if max_queued < 0:
            raise ValueError("max_queued must be >= 0")
        self.name = name
        self.max_concurrent = max_concurrent
        self.max_queued = max_queued
        self.acquire_timeout = acquire_timeout

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._in_flight = 0
        self._waiting = 0
        self._total_acquired = 0
        self._total_rejected = 0
        self._total_wait_time = 0.0

    @property
    def in_flight(self) -> int:
        """Number of currently in-flight requests."""
        return self._in_flight

    @property
    def available(self) -> int:
        """Remaining concurrency headroom."""
        return self.max_concurrent - self._in_flight

    @property
    def waiting(self) -> int:
        """Number of callers currently blocked on acquire."""
        return self._waiting

    @asynccontextmanager
    async def acquire(self, timeout: float | None = None) -> AsyncIterator[None]:
        """
        Acquire a slot for the duration of the `async with` block.

        Raises:
            BulkheadFullError: when the wait queue is full or the
                acquisition timeout elapses.
        """
        wait_timeout = self.acquire_timeout if timeout is None else timeout

        if self.max_queued == 0 and self._in_flight >= self.max_concurrent:
            self._total_rejected += 1
            raise BulkheadFullError(
                f"Bulkhead '{self.name}' full (no queue): "
                f"{self._in_flight}/{self.max_concurrent} in flight"
            )

        if self._waiting >= self.max_queued and self._in_flight >= self.max_concurrent:
            self._total_rejected += 1
            raise BulkheadFullError(
                f"Bulkhead '{self.name}' queue full: {self._waiting}/{self.max_queued} waiters"
            )

        self._waiting += 1
        start = time.time()
        try:
            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=wait_timeout)
            except asyncio.TimeoutError as exc:
                self._total_rejected += 1
                raise BulkheadFullError(
                    f"Bulkhead '{self.name}' acquire timed out after {wait_timeout:.2f}s"
                ) from exc
        finally:
            self._waiting -= 1

        self._total_wait_time += time.time() - start
        self._in_flight += 1
        self._total_acquired += 1
        try:
            yield
        finally:
            self._in_flight -= 1
            self._semaphore.release()

    def get_metrics(self) -> dict[str, Any]:
        """Snapshot of bulkhead utilization metrics."""
        avg_wait = self._total_wait_time / self._total_acquired if self._total_acquired else 0.0
        return {
            "name": self.name,
            "max_concurrent": self.max_concurrent,
            "max_queued": self.max_queued,
            "in_flight": self._in_flight,
            "available": self.available,
            "waiting": self._waiting,
            "total_acquired": self._total_acquired,
            "total_rejected": self._total_rejected,
            "avg_wait_seconds": round(avg_wait, 4),
            "rejection_rate": round(
                self._total_rejected / max(self._total_acquired + self._total_rejected, 1),
                4,
            ),
        }


class BulkheadRegistry:
    """
    Per-key bulkhead registry.

    Lazily creates a Bulkhead for each unique key (e.g., connector_id)
    so the orchestrator can isolate concurrency per upstream.
    """

    def __init__(
        self,
        default_max_concurrent: int = 10,
        default_max_queued: int = 50,
        default_acquire_timeout: float = 5.0,
    ):
        self.default_max_concurrent = default_max_concurrent
        self.default_max_queued = default_max_queued
        self.default_acquire_timeout = default_acquire_timeout
        self._bulkheads: dict[str, Bulkhead] = {}

    def for_key(self, key: str) -> Bulkhead:
        """Get (or lazily create) the Bulkhead for the given key."""
        if key not in self._bulkheads:
            self._bulkheads[key] = Bulkhead(
                name=key,
                max_concurrent=self.default_max_concurrent,
                max_queued=self.default_max_queued,
                acquire_timeout=self.default_acquire_timeout,
            )
        return self._bulkheads[key]

    def configure(
        self,
        key: str,
        max_concurrent: int,
        max_queued: int | None = None,
        acquire_timeout: float | None = None,
    ) -> Bulkhead:
        """Install or replace the Bulkhead for a specific key."""
        bh = Bulkhead(
            name=key,
            max_concurrent=max_concurrent,
            max_queued=(max_queued if max_queued is not None else self.default_max_queued),
            acquire_timeout=(
                acquire_timeout if acquire_timeout is not None else self.default_acquire_timeout
            ),
        )
        self._bulkheads[key] = bh
        return bh

    def get_all_metrics(self) -> dict[str, dict[str, Any]]:
        """Snapshot metrics for every registered bulkhead."""
        return {k: bh.get_metrics() for k, bh in self._bulkheads.items()}
