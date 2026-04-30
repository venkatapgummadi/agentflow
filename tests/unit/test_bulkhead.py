"""
Tests for the Bulkhead resilience pattern.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import asyncio

import pytest

from agentflow.resilience.bulkhead import (
    Bulkhead,
    BulkheadFullError,
    BulkheadRegistry,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestBulkheadBasic:
    def test_invalid_concurrency_rejected(self):
        with pytest.raises(ValueError):
            Bulkhead(max_concurrent=0)

    def test_invalid_queue_rejected(self):
        with pytest.raises(ValueError):
            Bulkhead(max_concurrent=1, max_queued=-1)

    def test_acquire_releases_slot(self):
        bh = Bulkhead(name="a", max_concurrent=2)

        async def use_one():
            async with bh.acquire():
                assert bh.in_flight == 1

        _run(use_one())
        assert bh.in_flight == 0
        assert bh.available == 2


class TestBulkheadConcurrency:
    def test_caps_concurrent_in_flight(self):
        bh = Bulkhead(name="cap", max_concurrent=2)
        peak = {"value": 0}

        async def task():
            async with bh.acquire():
                peak["value"] = max(peak["value"], bh.in_flight)
                await asyncio.sleep(0.02)

        async def runner():
            await asyncio.gather(*(task() for _ in range(5)))

        _run(runner())
        assert peak["value"] == 2

    def test_no_queue_rejects_immediately(self):
        bh = Bulkhead(name="nq", max_concurrent=1, max_queued=0)
        rejections = {"count": 0}

        async def first():
            async with bh.acquire():
                await asyncio.sleep(0.05)

        async def second():
            try:
                async with bh.acquire(timeout=0.5):
                    pass
            except BulkheadFullError:
                rejections["count"] += 1

        async def runner():
            t1 = asyncio.create_task(first())
            await asyncio.sleep(0.005)  # let t1 grab the slot
            await second()
            await t1

        _run(runner())
        assert rejections["count"] == 1

    def test_acquire_timeout(self):
        bh = Bulkhead(name="to", max_concurrent=1, max_queued=5)

        async def hold():
            async with bh.acquire():
                await asyncio.sleep(0.2)

        async def waiter():
            with pytest.raises(BulkheadFullError):
                async with bh.acquire(timeout=0.02):
                    pass

        async def runner():
            t1 = asyncio.create_task(hold())
            await asyncio.sleep(0.005)
            await waiter()
            await t1

        _run(runner())


class TestBulkheadMetrics:
    def test_metrics_track_acquired_and_rejected(self):
        bh = Bulkhead(name="m", max_concurrent=1, max_queued=0)

        async def successful():
            async with bh.acquire():
                pass

        _run(successful())
        _run(successful())

        async def fail_one():
            async with bh.acquire():
                # Try to acquire a second time concurrently — but since
                # we're sequential here, just simulate a forced reject.
                await asyncio.sleep(0)

        # Force a rejection by running two acquires concurrently
        async def collide():
            async def hold():
                async with bh.acquire():
                    await asyncio.sleep(0.05)

            async def reject():
                with pytest.raises(BulkheadFullError):
                    async with bh.acquire():
                        pass

            t1 = asyncio.create_task(hold())
            await asyncio.sleep(0.005)
            await reject()
            await t1

        _run(collide())

        metrics = bh.get_metrics()
        assert metrics["total_acquired"] >= 3
        assert metrics["total_rejected"] >= 1
        assert metrics["max_concurrent"] == 1


class TestBulkheadRegistry:
    def test_for_key_lazily_creates(self):
        reg = BulkheadRegistry(default_max_concurrent=4)
        bh = reg.for_key("conn-a")
        assert bh.name == "conn-a"
        assert bh.max_concurrent == 4
        # Same key returns same instance
        assert reg.for_key("conn-a") is bh

    def test_configure_overrides_defaults(self):
        reg = BulkheadRegistry(default_max_concurrent=4)
        bh = reg.configure("conn-b", max_concurrent=2)
        assert bh.max_concurrent == 2
        assert reg.for_key("conn-b") is bh

    def test_get_all_metrics(self):
        reg = BulkheadRegistry()
        reg.for_key("a")
        reg.for_key("b")
        all_metrics = reg.get_all_metrics()
        assert set(all_metrics.keys()) == {"a", "b"}
