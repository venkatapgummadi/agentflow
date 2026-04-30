"""
Tests for cyclic-workflow support.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

from agentflow.core.cyclic_workflow import CycleDetector, CyclicWorkflow, LoopEdge
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
