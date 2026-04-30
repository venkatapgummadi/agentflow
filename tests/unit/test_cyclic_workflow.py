"""
Tests for cyclic-workflow support.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import pytest

from agentflow.core.cyclic_workflow import (
    CycleDetector,
    CyclicExecutor,
    CyclicWorkflow,
    LoopEdge,
)
from agentflow.core.plan import ExecutionPlan, PlanStep


def _three_step_plan() -> ExecutionPlan:
    plan = ExecutionPlan(intent="poll then enrich")
    s1 = plan.add_step(name="poll_status", operation="GET /jobs/{id}")
    s2 = plan.add_step(name="check_ready", operation="local_check", depends_on=[s1.step_id])
    plan.add_step(name="finalize", operation="POST /jobs/{id}/done", depends_on=[s2.step_id])
    return plan


class TestCycleDetector:
    def test_pure_dag_has_no_cycles(self):
        plan = _three_step_plan()
        assert CycleDetector.is_dag(plan)
        assert CycleDetector.find_cycles(plan) == []

    def test_detects_simple_cycle(self):
        plan = _three_step_plan()
        # Inject a back edge: s1 depends on s3 (so s1 -> s3 -> s1).
        plan.steps[0].depends_on.append(plan.steps[2].step_id)
        cycles = CycleDetector.find_cycles(plan)
        assert cycles, "expected at least one cycle"
        assert any(len(c) >= 2 for c in cycles)


class TestCyclicWorkflow:
    def test_unroll_doubles_body_for_two_iterations(self):
        plan = _three_step_plan()
        head, _, tail = plan.steps
        cw = CyclicWorkflow(plan=plan)
        cw.add_loop(head_step_id=head.step_id, tail_step_id=tail.step_id, max_iterations=2)
        unrolled = cw.unroll()
        # original 3 + 1 extra iteration of 3 = 6
        assert len(unrolled.steps) == 6
        # the unrolled DAG must remain acyclic
        assert CycleDetector.is_dag(unrolled)

    def test_unroll_chains_iterations_via_tail(self):
        plan = _three_step_plan()
        head, _, tail = plan.steps
        cw = CyclicWorkflow(plan=plan)
        cw.add_loop(head_step_id=head.step_id, tail_step_id=tail.step_id, max_iterations=3)
        unrolled = cw.unroll()
        # the second iteration's head must depend on the first iteration's tail
        first_tail_id = unrolled.steps[2].step_id
        second_head = unrolled.get_step(plan.steps[0].step_id + "_i1")
        assert second_head is not None
        assert first_tail_id in second_head.depends_on

    def test_max_total_steps_is_respected(self):
        plan = _three_step_plan()
        head, _, tail = plan.steps
        cw = CyclicWorkflow(plan=plan, max_total_steps=4)
        cw.add_loop(head_step_id=head.step_id, tail_step_id=tail.step_id, max_iterations=10)
        unrolled = cw.unroll()
        assert len(unrolled.steps) <= 4

    def test_unknown_step_ids_raise(self):
        plan = _three_step_plan()
        cw = CyclicWorkflow(plan=plan)
        cw.add_loop(head_step_id="missing", tail_step_id=plan.steps[2].step_id)
        try:
            cw.unroll()
        except ValueError as exc:
            assert "missing" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected ValueError")

    def test_loop_edge_dataclass_defaults(self):
        e = LoopEdge(head_step_id="a", tail_step_id="b")
        assert e.max_iterations == 5
        assert e.terminate_when is None

    def test_unrolled_plan_is_executable_shape(self):
        """Smoke: unrolled plan exposes the same DAG API as the original."""
        plan = _three_step_plan()
        cw = CyclicWorkflow(plan=plan)
        cw.add_loop(plan.steps[0].step_id, plan.steps[2].step_id, max_iterations=2)
        unrolled = cw.unroll()
        assert hasattr(unrolled, "get_ready_steps")
        ready = unrolled.get_ready_steps()
        # only the very first head should be ready initially
        assert len(ready) == 1


def test_clone_preserves_definition():
    from agentflow.core.cyclic_workflow import _clone

    s = PlanStep(name="x", operation="GET /x", parameters={"a": 1}, timeout_ms=42)
    c = _clone(s, suffix="_i1")
    assert c.name.endswith("_i1")
    assert c.parameters == {"a": 1}
    assert c.timeout_ms == 42
    # mutating clone does not affect original
    c.parameters["b"] = 2
    assert "b" not in s.parameters


# ── runtime CyclicExecutor tests ─────────────────────────────────────────



@pytest.mark.asyncio
async def test_cyclic_executor_runs_to_max_when_no_terminator():
    plan = _three_step_plan()
    cw = CyclicWorkflow(plan=plan)
    cw.add_loop(plan.steps[0].step_id, plan.steps[2].step_id, max_iterations=4)

    calls: list[int] = []

    async def runner(plan, iter_idx):
        calls.append(iter_idx)
        return {"iter": iter_idx, "status": "pending"}

    executor = CyclicExecutor(run_iteration=runner)
    history = await executor.run(cw)
    assert calls == [0, 1, 2, 3]
    assert len(history) == 4


@pytest.mark.asyncio
async def test_cyclic_executor_terminates_early():
    plan = _three_step_plan()
    cw = CyclicWorkflow(plan=plan)

    async def stop_at_2(outputs, iter_idx):
        return outputs.get("iter") == 2

    cw.add_loop(
        plan.steps[0].step_id,
        plan.steps[2].step_id,
        max_iterations=10,
        terminate_when=stop_at_2,
    )

    async def runner(plan, iter_idx):
        return {"iter": iter_idx}

    history = await CyclicExecutor(run_iteration=runner).run(cw)
    assert len(history) == 3  # 0, 1, 2 — stopped after seeing iter==2


@pytest.mark.asyncio
async def test_cyclic_executor_handles_predicate_exception():
    plan = _three_step_plan()
    cw = CyclicWorkflow(plan=plan)

    def bad(outputs, iter_idx):
        raise RuntimeError("boom")

    cw.add_loop(plan.steps[0].step_id, plan.steps[2].step_id, max_iterations=2, terminate_when=bad)

    async def runner(plan, iter_idx):
        return {}

    history = await CyclicExecutor(run_iteration=runner).run(cw)
    # predicate failures are treated as "do not terminate" -> runs to max
    assert len(history) == 2


@pytest.mark.asyncio
async def test_cyclic_executor_no_loop_runs_once():
    plan = _three_step_plan()
    cw = CyclicWorkflow(plan=plan)

    async def runner(plan, iter_idx):
        return {"once": True}

    history = await CyclicExecutor(run_iteration=runner).run(cw)
    assert history == [{"once": True}]


@pytest.mark.asyncio
async def test_cyclic_executor_supports_sync_runner_and_predicate():
    plan = _three_step_plan()
    cw = CyclicWorkflow(plan=plan)

    def stop_at_1(outputs, iter_idx):
        return iter_idx == 1

    cw.add_loop(
        plan.steps[0].step_id,
        plan.steps[2].step_id,
        max_iterations=5,
        terminate_when=stop_at_1,
    )

    def runner(plan, iter_idx):  # sync
        return {"iter": iter_idx}

    history = await CyclicExecutor(run_iteration=runner).run(cw)
    assert len(history) == 2


# ── safety guards added in v1.1.2 ────────────────────────────────────────


def test_unroll_rejects_cyclic_input_plan():
    plan = _three_step_plan()
    # inject a back-edge so the input is cyclic
    plan.steps[0].depends_on.append(plan.steps[2].step_id)
    cw = CyclicWorkflow(plan=plan)
    cw.add_loop(plan.steps[0].step_id, plan.steps[2].step_id, max_iterations=2)
    with pytest.raises(ValueError, match="cycle"):
        cw.unroll()


@pytest.mark.asyncio
async def test_cyclic_executor_rejects_multi_loop():
    plan = _three_step_plan()
    cw = CyclicWorkflow(plan=plan)
    cw.add_loop(plan.steps[0].step_id, plan.steps[2].step_id, max_iterations=2)
    cw.add_loop(plan.steps[0].step_id, plan.steps[2].step_id, max_iterations=2)

    async def runner(p, i):
        return {}

    with pytest.raises(NotImplementedError, match="single top-level loop"):
        await CyclicExecutor(run_iteration=runner).run(cw)
