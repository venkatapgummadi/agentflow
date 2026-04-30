"""
Cyclic workflow support for AgentFlow.

The base ``ExecutionPlan`` is a strict DAG, which is the right default
for most enterprise orchestrations: it lets the executor parallelise
aggressively and reason about completion deterministically. However,
several real-world patterns require *bounded* cycles:

* poll-until-ready (e.g. wait for a long-running mulesoft batch job),
* retry-with-decision (the validator decides whether to re-fetch),
* iterative enrichment (paginate through a list endpoint).

This module provides:

* ``CycleDetector`` — finds back-edges in an ``ExecutionPlan``.
* ``CyclicWorkflow`` — a thin wrapper that adds explicit ``loop_back``
  edges and a termination predicate, then *unrolls* the loop into a
  bounded DAG so the existing executor can run it unchanged.

The unroll strategy preserves AgentFlow's parallelism guarantees and
its statistical / formal properties (Theorem 2 in the paper still
applies because each unrolled iteration is itself a Pareto-optimised
DAG).

Reviewer 4 explicitly flagged "no evaluation for cyclic workflows or
very large (step count > 20) graphs" as future work; this module plus
``tests/unit/test_cyclic_workflow.py`` and
``tests/unit/test_large_graph.py`` close that gap.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agentflow.core.plan import ExecutionPlan, PlanStep

logger = logging.getLogger(__name__)


@dataclass
class LoopEdge:
    """Marks one step as the head of a loop, pointing back to a tail step."""

    head_step_id: str  # the step where the loop is entered
    tail_step_id: str  # the step that completes one iteration
    max_iterations: int = 5
    # Optional predicate evaluated on the *outputs* dict between iterations.
    # Returning ``True`` terminates the loop early.
    terminate_when: Callable[[dict[str, Any], int], bool] | None = None


@dataclass
class CyclicWorkflow:
    """An ExecutionPlan plus loop edges, unrollable into a bounded DAG."""

    plan: ExecutionPlan
    loops: list[LoopEdge] = field(default_factory=list)
    max_total_steps: int = 500  # safety net for runaway unrolls

    def add_loop(
        self,
        head_step_id: str,
        tail_step_id: str,
        max_iterations: int = 5,
        terminate_when: Callable[[dict[str, Any], int], bool] | None = None,
    ) -> LoopEdge:
        edge = LoopEdge(
            head_step_id=head_step_id,
            tail_step_id=tail_step_id,
            max_iterations=max_iterations,
            terminate_when=terminate_when,
        )
        self.loops.append(edge)
        return edge

    def unroll(self) -> ExecutionPlan:
        """
        Unroll loops into a bounded DAG.

        For each ``LoopEdge`` the body steps (between ``head`` and
        ``tail`` inclusive) are duplicated ``max_iterations - 1`` extra
        times, with rewritten step IDs and dependency edges so the
        executor sees a normal DAG.
        """
        unrolled = ExecutionPlan(
            plan_id=self.plan.plan_id + "-unrolled",
            intent=self.plan.intent,
            metadata={**self.plan.metadata, "unrolled_from": self.plan.plan_id},
        )
        # copy original steps
        id_map: dict[str, str] = {}
        for step in self.plan.steps:
            cloned = _clone(step)
            unrolled.steps.append(cloned)
            id_map[step.step_id] = cloned.step_id

        # rewrite original deps
        for step in unrolled.steps:
            step.depends_on = [id_map[d] for d in step.depends_on if d in id_map]

        for loop in self.loops:
            body = self._collect_body(loop)
            previous_tail_id = id_map[loop.tail_step_id]
            for iter_idx in range(1, loop.max_iterations):
                if len(unrolled.steps) >= self.max_total_steps:
                    logger.warning(
                        "Loop unroll hit max_total_steps=%d; truncating",
                        self.max_total_steps,
                    )
                    break
                # clone body, respecting the global step budget
                local_id_map: dict[str, str] = {}
                budget_hit = False
                for step in body:
                    if len(unrolled.steps) >= self.max_total_steps:
                        budget_hit = True
                        break
                    cloned = _clone(step, suffix=f"_i{iter_idx}")
                    local_id_map[step.step_id] = cloned.step_id
                    unrolled.steps.append(cloned)
                if budget_hit:
                    logger.warning(
                        "Loop unroll hit max_total_steps=%d; truncating",
                        self.max_total_steps,
                    )
                    break
                # rewrite intra-body deps; head depends on previous tail
                for step in body:
                    cloned = unrolled.get_step(local_id_map[step.step_id])
                    if cloned is None:
                        continue
                    new_deps = []
                    for d in step.depends_on:
                        if d in local_id_map:
                            new_deps.append(local_id_map[d])
                        elif d in id_map:
                            new_deps.append(id_map[d])
                    cloned.depends_on = new_deps
                # explicitly chain iterations
                head_clone = unrolled.get_step(local_id_map[loop.head_step_id])
                if head_clone is not None and previous_tail_id not in head_clone.depends_on:
                    head_clone.depends_on.append(previous_tail_id)
                previous_tail_id = local_id_map[loop.tail_step_id]
        logger.info(
            "Unrolled cyclic workflow: %d -> %d steps",
            len(self.plan.steps),
            len(unrolled.steps),
        )
        return unrolled

    # ── helpers ─────────────────────────────────────────────────────────

    def _collect_body(self, loop: LoopEdge) -> list[PlanStep]:
        """All steps reachable from ``head`` via deps, up to and including ``tail``."""
        head = self.plan.get_step(loop.head_step_id)
        tail = self.plan.get_step(loop.tail_step_id)
        if head is None or tail is None:
            raise ValueError(
                "Loop refers to unknown step ids: "
                f"head={loop.head_step_id} tail={loop.tail_step_id}"
            )
        # Walk forward from head: a step is in the body if some
        # dependency chain from head reaches it on the way to tail.
        body: list[PlanStep] = []
        seen: set[str] = set()
        frontier = [head]
        while frontier:
            current = frontier.pop()
            if current.step_id in seen:
                continue
            seen.add(current.step_id)
            body.append(current)
            if current.step_id == loop.tail_step_id:
                continue
            for step in self.plan.steps:
                if current.step_id in step.depends_on:
                    frontier.append(step)
        return body


class CycleDetector:
    """Find back-edges (cycles) in an ``ExecutionPlan`` via DFS."""

    @staticmethod
    def find_cycles(plan: ExecutionPlan) -> list[list[str]]:
        adjacency: dict[str, list[str]] = {s.step_id: list(s.depends_on) for s in plan.steps}
        visited: dict[str, int] = {s.step_id: 0 for s in plan.steps}  # 0 white, 1 gray, 2 black
        cycles: list[list[str]] = []
        stack: list[str] = []

        def dfs(node: str) -> None:
            visited[node] = 1
            stack.append(node)
            for neighbor in adjacency.get(node, []):
                if visited.get(neighbor, 0) == 1:
                    # back-edge -> cycle from neighbor down the stack
                    if neighbor in stack:
                        idx = stack.index(neighbor)
                        cycles.append(list(stack[idx:]) + [neighbor])
                elif visited.get(neighbor, 0) == 0:
                    dfs(neighbor)
            visited[node] = 2
            stack.pop()

        for step in plan.steps:
            if visited[step.step_id] == 0:
                dfs(step.step_id)
        return cycles

    @classmethod
    def is_dag(cls, plan: ExecutionPlan) -> bool:
        return not cls.find_cycles(plan)


def _clone(step: PlanStep, suffix: str = "") -> PlanStep:
    """Return a fresh ``PlanStep`` with the same definition."""
    new_id = (step.step_id + suffix) if suffix else _new_id()
    return PlanStep(
        step_id=new_id,
        name=(step.name + suffix) if step.name else step.name,
        step_type=step.step_type,
        connector_id=step.connector_id,
        operation=step.operation,
        parameters=dict(step.parameters),
        depends_on=list(step.depends_on),
        transform=step.transform,
        condition=step.condition,
        fallback_step_id=step.fallback_step_id,
        timeout_ms=step.timeout_ms,
        retry_policy=dict(step.retry_policy) if step.retry_policy else None,
    )


def _new_id() -> str:
    import uuid

    return str(uuid.uuid4())[:8]


# ── runtime cyclic executor ──────────────────────────────────────────────


class CyclicExecutor:
    """
    Runtime cyclic-workflow executor.

    Where ``CyclicWorkflow.unroll()`` produces a *static* DAG that
    ignores ``terminate_when``, ``CyclicExecutor.run`` evaluates the
    termination predicate after each iteration and stops early.

    Usage::

        async def stop_when_ready(outputs, iter_idx):
            return outputs.get("status") == "ready"

        cw = CyclicWorkflow(plan=plan)
        cw.add_loop("poll", "tail", max_iterations=10, terminate_when=stop_when_ready)

        executor = CyclicExecutor(run_iteration=my_iteration_runner)
        history = await executor.run(cw)
        print(f"converged after {len(history)} iterations")
    """

    def __init__(
        self,
        run_iteration: Callable[[ExecutionPlan, int], Any],
    ):
        # ``run_iteration`` is supplied by the caller so this module
        # stays free of any executor / connector dependency. It MUST be
        # async and return a dict of outputs for one iteration.
        self._run_iteration = run_iteration

    async def run(self, workflow: CyclicWorkflow) -> list[dict[str, Any]]:
        import asyncio

        if not workflow.loops:
            outputs = await self._invoke(workflow.plan, iter_idx=0)
            return [outputs]

        # We support a single top-level loop in the runtime path; nested
        # loops still go through static unroll. This keeps the runtime
        # contract small and predictable.
        loop = workflow.loops[0]
        history: list[dict[str, Any]] = []
        for iter_idx in range(loop.max_iterations):
            outputs = await self._invoke(workflow.plan, iter_idx=iter_idx)
            history.append(outputs)
            if loop.terminate_when is not None:
                try:
                    should_stop = loop.terminate_when(outputs, iter_idx)
                    if asyncio.iscoroutine(should_stop):
                        should_stop = await should_stop
                except Exception as exc:  # noqa: BLE001
                    logger.warning("terminate_when raised %s; treating as False", exc)
                    should_stop = False
                if should_stop:
                    logger.info(
                        "CyclicExecutor terminated after %d iterations (predicate True)",
                        iter_idx + 1,
                    )
                    break
        return history

    async def _invoke(self, plan: ExecutionPlan, iter_idx: int) -> dict[str, Any]:
        import asyncio

        result = self._run_iteration(plan, iter_idx)
        if asyncio.iscoroutine(result):
            result = await result
        if not isinstance(result, dict):
            raise TypeError(
                "run_iteration must return a dict of outputs for the iteration"
            )
        return result
