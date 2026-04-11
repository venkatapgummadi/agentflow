"""
Tests for ExecutionPlan and PlanStep.

Verifies DAG construction, topological ordering, and step lifecycle.

Author: Venkata Pavan Kumar Gummadi
"""

from agentflow.core.plan import ExecutionPlan, PlanStep, StepStatus


class TestPlanStep:
    """Test PlanStep lifecycle."""

    def test_initial_status_is_pending(self):
        step = PlanStep(name="test_step")
        assert step.status == StepStatus.PENDING

    def test_mark_running(self):
        step = PlanStep(name="test_step")
        step.mark_running()
        assert step.status == StepStatus.RUNNING

    def test_mark_completed(self):
        step = PlanStep(name="test_step")
        step.mark_completed(result={"data": 42})
        assert step.status == StepStatus.COMPLETED
        assert step.result == {"data": 42}

    def test_mark_failed(self):
        step = PlanStep(name="test_step")
        step.mark_failed("Connection timeout")
        assert step.status == StepStatus.FAILED
        assert step.error == "Connection timeout"

    def test_is_terminal(self):
        step = PlanStep(name="test_step")
        assert step.is_terminal is False
        step.mark_completed(None)
        assert step.is_terminal is True


class TestExecutionPlan:
    """Test ExecutionPlan DAG operations."""

    def test_add_step(self):
        plan = ExecutionPlan(intent="test")
        step = plan.add_step(name="step1", operation="GET /api")
        assert len(plan.steps) == 1
        assert step.name == "step1"

    def test_get_step(self):
        plan = ExecutionPlan(intent="test")
        step = plan.add_step(name="step1")
        found = plan.get_step(step.step_id)
        assert found is step

    def test_get_ready_steps_no_dependencies(self):
        plan = ExecutionPlan(intent="test")
        plan.add_step(name="step1")
        plan.add_step(name="step2")
        ready = plan.get_ready_steps()
        assert len(ready) == 2

    def test_get_ready_steps_with_dependencies(self):
        plan = ExecutionPlan(intent="test")
        s1 = plan.add_step(name="step1")
        plan.add_step(name="step2", depends_on=[s1.step_id])

        ready = plan.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].name == "step1"

    def test_get_ready_steps_after_completion(self):
        plan = ExecutionPlan(intent="test")
        s1 = plan.add_step(name="step1")
        plan.add_step(name="step2", depends_on=[s1.step_id])

        s1.mark_completed("done")
        ready = plan.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].name == "step2"

    def test_is_complete(self):
        plan = ExecutionPlan(intent="test")
        s1 = plan.add_step(name="step1")
        s2 = plan.add_step(name="step2")

        assert plan.is_complete is False
        s1.mark_completed(None)
        assert plan.is_complete is False
        s2.mark_completed(None)
        assert plan.is_complete is True

    def test_success_rate(self):
        plan = ExecutionPlan(intent="test")
        s1 = plan.add_step(name="step1")
        s2 = plan.add_step(name="step2")

        s1.mark_completed(None)
        s2.mark_failed("error")
        assert plan.success_rate == 0.5

    def test_topological_order(self):
        plan = ExecutionPlan(intent="test")
        s1 = plan.add_step(name="step1")
        s2 = plan.add_step(name="step2", depends_on=[s1.step_id])
        plan.add_step(name="step3", depends_on=[s2.step_id])

        order = plan.topological_order()
        names = [s.name for s in order]
        assert names == ["step1", "step2", "step3"]

    def test_topological_order_parallel(self):
        plan = ExecutionPlan(intent="test")
        s1 = plan.add_step(name="step1")
        s2 = plan.add_step(name="step2")
        plan.add_step(name="step3", depends_on=[s1.step_id, s2.step_id])

        order = plan.topological_order()
        names = [s.name for s in order]
        assert names[-1] == "step3"
        assert set(names[:2]) == {"step1", "step2"}
