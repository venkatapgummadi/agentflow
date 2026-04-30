"""
Execution Plan — structured representation of API orchestration workflows.

An ExecutionPlan is a directed acyclic graph (DAG) of PlanSteps that
the Executor agent traverses. Steps can run in parallel when their
dependencies allow, and each step maps to a concrete API call.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StepStatus(Enum):
    """Lifecycle states for a plan step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class StepType(Enum):
    """Categories of plan steps."""

    API_CALL = "api_call"
    TRANSFORM = "transform"
    CONDITION = "condition"
    PARALLEL_GROUP = "parallel_group"
    AGGREGATE = "aggregate"
    VALIDATE = "validate"


@dataclass
class PlanStep:
    """
    A single step in an execution plan.

    Each step represents an atomic operation — typically an API call
    with optional data transformation, conditional logic, or validation.

    Attributes:
        step_id: Unique identifier for this step.
        step_type: Category of operation (api_call, transform, etc.).
        connector_id: Which connector handles this step.
        operation: The specific operation to invoke (e.g., "GET /customers/{id}").
        parameters: Input parameters for the operation.
        depends_on: Step IDs that must complete before this step runs.
        transform: Optional JMESPath or JSONPath expression to reshape output.
        condition: Optional boolean expression; step is skipped if false.
        fallback_step_id: Step to execute if this step fails.
        timeout_ms: Maximum execution time in milliseconds.
        retry_policy: Retry configuration for transient failures.
    """

    step_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    step_type: StepType = StepType.API_CALL
    connector_id: str = ""
    operation: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    transform: str | None = None
    condition: str | None = None
    fallback_step_id: str | None = None
    timeout_ms: int = 30000
    retry_policy: dict[str, Any] | None = None
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str | None = None

    def mark_running(self) -> None:
        self.status = StepStatus.RUNNING

    def mark_completed(self, result: Any) -> None:
        self.status = StepStatus.COMPLETED
        self.result = result

    def mark_failed(self, error: str) -> None:
        self.status = StepStatus.FAILED
        self.error = error

    def mark_skipped(self, reason: str = "") -> None:
        self.status = StepStatus.SKIPPED
        self.error = reason

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            StepStatus.COMPLETED,
            StepStatus.FAILED,
            StepStatus.SKIPPED,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "step_type": self.step_type.value,
            "connector_id": self.connector_id,
            "operation": self.operation,
            "parameters": self.parameters,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "has_result": self.result is not None,
            "error": self.error,
        }


@dataclass
class ExecutionPlan:
    """
    A DAG of PlanSteps representing an API orchestration workflow.

    The plan is created by the PlannerAgent and executed by the
    ExecutorAgent. Steps with no unmet dependencies can run in parallel.

    Usage:
        plan = ExecutionPlan(intent="Fetch and enrich customer")
        step1 = plan.add_step(name="fetch_customer", operation="GET /customers/123")
        step2 = plan.add_step(name="get_credit", depends_on=[step1.step_id])
        ready = plan.get_ready_steps()  # [step1] initially
    """

    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    intent: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_step(self, **kwargs: Any) -> PlanStep:
        """Create and add a step to the plan."""
        step = PlanStep(**kwargs)
        self.steps.append(step)
        return step

    def get_step(self, step_id: str) -> PlanStep | None:
        """Retrieve a step by ID."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def get_ready_steps(self) -> list[PlanStep]:
        """
        Get all steps whose dependencies are satisfied and are pending.

        This enables maximum parallelism: any step whose predecessors
        have completed (or that has no dependencies) is ready to execute.
        """
        completed_ids = {
            s.step_id for s in self.steps if s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
        }
        ready = []
        for step in self.steps:
            if step.status != StepStatus.PENDING:
                continue
            if all(dep in completed_ids for dep in step.depends_on):
                ready.append(step)
        return ready

    @property
    def is_complete(self) -> bool:
        """Check if all steps have reached a terminal state."""
        return all(step.is_terminal for step in self.steps)

    @property
    def has_failures(self) -> bool:
        return any(s.status == StepStatus.FAILED for s in self.steps)

    @property
    def success_rate(self) -> float:
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        return completed / len(self.steps)

    def topological_order(self) -> list[PlanStep]:
        """Return steps in dependency-respecting order (Kahn's algorithm)."""
        in_degree: dict[str, int] = {s.step_id: 0 for s in self.steps}
        adj: dict[str, list[str]] = {s.step_id: [] for s in self.steps}

        for step in self.steps:
            for dep in step.depends_on:
                if dep in adj:
                    adj[dep].append(step.step_id)
                    in_degree[step.step_id] += 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        ordered: list[PlanStep] = []

        while queue:
            current = queue.pop(0)
            current_step = self.get_step(current)
            if current_step is not None:
                ordered.append(current_step)
            for neighbor in adj.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return ordered

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "intent": self.intent,
            "steps": [s.to_dict() for s in self.steps],
            "is_complete": self.is_complete,
            "success_rate": self.success_rate,
            "metadata": self.metadata,
        }
