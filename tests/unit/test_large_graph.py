"""
Stress tests for very large execution plans.

Reviewer 4 explicitly noted that the original evaluation lacked
results for "step count > 20" workflows. These tests exercise the
planner-level data structures (``ExecutionPlan``, topological order,
ready-step computation, cycle detection) on graphs of 50, 100 and 500
steps to demonstrate that the runtime cost remains tractable.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import time

import pytest

from agentflow.core.cyclic_workflow import CycleDetector
from agentflow.core.plan import ExecutionPlan, StepStatus


def _build_dag(n: int, fanout: int = 2) -> ExecutionPlan:
    """A wide-then-narrow DAG with ``n`` steps, each depending on up to ``fanout`` predecessors."""
    plan = ExecutionPlan(intent=f"large_dag_{n}")
    for i in range(n):
        deps = [plan.steps[j].step_id for j in range(max(0, i - fanout), i)]
        plan.add_step(name=f"s{i}", operation=f"GET /resource/{i}", depends_on=deps)
    return plan


@pytest.mark.parametrize("n", [50, 100, 500])
def test_topological_order_returns_all_steps(n: int):
    plan = _build_dag(n)
    started = time.perf_counter()
    ordered = plan.topological_order()
    elapsed = time.perf_counter() - started
    assert len(ordered) == n
    # ordering must respect dependencies
    pos = {s.step_id: i for i, s in enumerate(ordered)}
    for s in plan.steps:
        for d in s.depends_on:
            assert pos[d] < pos[s.step_id]
    # generous bound: 500-node DAG should still topo-sort in <250ms
    assert elapsed < 0.25, f"too slow: {elapsed*1000:.1f}ms for n={n}"


@pytest.mark.parametrize("n", [50, 100, 500])
def test_ready_steps_iteration_completes(n: int):
    """Drive the plan to completion via ``get_ready_steps`` to ensure no deadlock."""
    plan = _build_dag(n)
    iterations = 0
    while not plan.is_complete:
        ready = plan.get_ready_steps()
        assert ready, f"deadlock at iteration {iterations}"
        for step in ready:
            step.status = StepStatus.COMPLETED
        iterations += 1
        assert iterations <= n + 5, "loop did not converge"
    assert plan.success_rate == 0.0 or plan.success_rate == 1.0


@pytest.mark.parametrize("n", [50, 200])
def test_cycle_detector_scales(n: int):
    plan = _build_dag(n)
    started = time.perf_counter()
    assert CycleDetector.is_dag(plan)
    elapsed = time.perf_counter() - started
    assert elapsed < 0.5, f"cycle detection too slow: {elapsed*1000:.1f}ms"


def test_introducing_back_edge_in_large_graph_is_detected():
    plan = _build_dag(100)
    # back-edge: first step now depends on the last
    plan.steps[0].depends_on.append(plan.steps[-1].step_id)
    assert not CycleDetector.is_dag(plan)
    cycles = CycleDetector.find_cycles(plan)
    assert cycles
