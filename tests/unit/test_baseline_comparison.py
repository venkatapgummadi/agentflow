"""
Smoke tests for the baseline-comparison harness.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import math

import pytest

from benchmarks.baseline_comparison import (
    ADAPTERS,
    DEFAULT_CALIBRATION,
    AgentFlowAdapter,
    LangChainStubAdapter,
    benchmark_one,
    run_all,
    speedup_table,
)


@pytest.mark.asyncio
async def test_each_adapter_runs_one_workflow():
    for name, cls in ADAPTERS.items():
        adapter = cls(DEFAULT_CALIBRATION)
        ok = await adapter.run_workflow(4)
        assert ok is True


@pytest.mark.asyncio
async def test_benchmark_one_returns_metrics():
    adapter = AgentFlowAdapter(DEFAULT_CALIBRATION)
    result = await benchmark_one(adapter, workflows=20, concurrency=10, n_steps=4)
    assert result.workflows == 20
    assert result.throughput_rps > 0
    assert result.error_rate == 0.0
    assert result.memory_mb_steady == 48


@pytest.mark.asyncio
async def test_run_all_includes_every_framework():
    results = await run_all(workflows=10, concurrency=5, n_steps=4, calibration=DEFAULT_CALIBRATION)
    names = {r.framework for r in results}
    assert names == set(ADAPTERS.keys())


@pytest.mark.asyncio
async def test_agentflow_is_fastest_or_competitive():
    """Sanity check: AgentFlow's stub should be at least as fast as LangChain's."""
    af = await benchmark_one(AgentFlowAdapter(DEFAULT_CALIBRATION), 50, 10, 8)
    lc = await benchmark_one(LangChainStubAdapter(DEFAULT_CALIBRATION), 50, 10, 8)
    assert af.throughput_rps >= lc.throughput_rps


@pytest.mark.asyncio
async def test_speedup_table_baseline_is_one():
    # use a larger workload so timing variance does not flip the ranking
    results = await run_all(100, 20, 8, DEFAULT_CALIBRATION)
    speedups = speedup_table(results)
    assert pytest.approx(speedups["agentflow"], abs=1e-3) == 1.0
    # AgentFlow uses work-stealing; under a meaningfully sized workload its
    # throughput should not fall below the slowest sequential baseline
    assert speedups["langchain"] >= 1.0
    assert speedups["apache_camel"] >= 1.0

def test_speedup_table_sentinel_for_zero_throughput():
    from benchmarks.baseline_comparison import BenchmarkResult, speedup_table

    af = BenchmarkResult("agentflow", 1, 1, 1.0, 1.0, 1.0, 1.0, 1000.0, 0.0, 48)
    zero = BenchmarkResult("langchain", 1, 1, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 142)
    speedups = speedup_table([af, zero])
    assert speedups["agentflow"] == 1.0
    assert math.isinf(speedups["langchain"])
