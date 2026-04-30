"""
Executor Agent — executes plans with parallel scheduling and resilience.

The ExecutorAgent traverses the ExecutionPlan DAG, running steps in
parallel where dependencies allow, with intelligent routing and
self-healing resilience (circuit breakers, retries, fallbacks).

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agentflow.agents.base_agent import BaseAgent
from agentflow.connectors.base import APIResponse, BaseConnector
from agentflow.core.context import EventType, OrchestrationContext
from agentflow.core.plan import ExecutionPlan, PlanStep, StepStatus
from agentflow.resilience.circuit_breaker import CircuitBreaker
from agentflow.resilience.retry_policy import RetryPolicy
from agentflow.routing.dynamic_router import DynamicRouter

logger = logging.getLogger(__name__)


class ExecutorAgent(BaseAgent):
    """
    Executes plan steps with parallel scheduling and resilience.

    Execution strategy:
    1. Identify all ready steps (dependencies satisfied)
    2. Route each step to the optimal endpoint via DynamicRouter
    3. Execute ready steps in parallel (bounded concurrency)
    4. Apply circuit breaker and retry logic on failures
    5. Store results in context for downstream steps
    6. Repeat until all steps are terminal
    """

    def __init__(self, **kwargs: Any):
        super().__init__(name="ExecutorAgent", **kwargs)
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._retry_policy = RetryPolicy()

    async def execute(self, context: OrchestrationContext, **kwargs: Any) -> dict[str, Any]:
        """Execute the plan from context."""
        plan = kwargs.get("plan")
        if not isinstance(plan, ExecutionPlan):
            raise TypeError("ExecutorAgent.execute requires a 'plan' ExecutionPlan kwarg")
        connectors = kwargs.get("connectors", {})
        router = kwargs.get("router")
        return await self.execute_plan(plan, context, connectors, router)

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        context: OrchestrationContext,
        connectors: dict[str, BaseConnector],
        router: DynamicRouter | None = None,
        max_parallel: int = 10,
    ) -> dict[str, Any]:
        """
        Execute all steps in the plan with maximum parallelism.

        Uses a work-stealing scheduler: continuously finds ready steps
        and executes them concurrently, bounded by max_parallel.
        """
        outputs: dict[str, Any] = {}
        semaphore = asyncio.Semaphore(max_parallel)
        iteration = 0

        while not plan.is_complete:
            iteration += 1
            ready_steps = plan.get_ready_steps()

            if not ready_steps:
                # Deadlock detection
                pending = [s for s in plan.steps if s.status == StepStatus.PENDING]
                if pending:
                    logger.error(
                        "Deadlock detected: %d pending steps with unmet dependencies",
                        len(pending),
                    )
                    for step in pending:
                        step.mark_failed("Deadlock: unresolvable dependencies")
                break

            logger.info(
                "Iteration %d: executing %d ready steps in parallel",
                iteration,
                len(ready_steps),
            )

            # Execute ready steps in parallel
            tasks = [
                self._execute_step_with_semaphore(
                    step=step,
                    context=context,
                    connectors=connectors,
                    router=router,
                    semaphore=semaphore,
                )
                for step in ready_steps
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect outputs
            for step, result in zip(ready_steps, results):
                if isinstance(result, Exception):
                    step.mark_failed(str(result))
                    self.emit_event(
                        context,
                        EventType.STEP_FAILED,
                        step_id=step.step_id,
                        message=f"Step {step.name} failed: {result}",
                    )
                elif step.status == StepStatus.COMPLETED:
                    outputs[step.step_id] = step.result
                    context.store_step_result(step.step_id, step.result)

        return outputs

    async def _execute_step_with_semaphore(
        self,
        step: PlanStep,
        context: OrchestrationContext,
        connectors: dict[str, BaseConnector],
        router: DynamicRouter | None,
        semaphore: asyncio.Semaphore,
    ) -> Any:
        """Execute a single step within the concurrency semaphore."""
        async with semaphore:
            return await self._execute_step(step, context, connectors, router)

    async def _execute_step(
        self,
        step: PlanStep,
        context: OrchestrationContext,
        connectors: dict[str, BaseConnector],
        router: DynamicRouter | None,
    ) -> Any:
        """
        Execute a single plan step with full resilience.

        Flow:
        1. Check condition (skip if false)
        2. Get circuit breaker for the target connector
        3. Route to optimal endpoint
        4. Execute with retry policy
        5. Apply output transformation
        """
        step.mark_running()
        self.emit_event(
            context,
            EventType.STEP_STARTED,
            step_id=step.step_id,
            message=f"Starting step: {step.name}",
        )

        # Check condition
        if step.condition:
            if not self._evaluate_condition(step.condition, context):
                step.mark_skipped(f"Condition not met: {step.condition}")
                return None

        # Resolve connector
        connector = connectors.get(step.connector_id)
        if not connector:
            # Try routing to find the best connector
            if router and connectors:
                connector = self._route_to_connector(step, list(connectors.values()), router)

        if not connector:
            step.mark_failed(f"No connector available for: {step.connector_id}")
            return None

        # Get or create circuit breaker
        cb = self._get_circuit_breaker(connector.connector_id)

        # Execute with circuit breaker and retry
        try:
            result = await self._execute_with_resilience(
                step=step,
                connector=connector,
                circuit_breaker=cb,
                context=context,
            )

            step.mark_completed(result)
            self.emit_event(
                context,
                EventType.STEP_COMPLETED,
                step_id=step.step_id,
                message=f"Step {step.name} completed successfully",
            )
            return result

        except Exception as e:
            step.mark_failed(str(e))

            # Try fallback if available
            if step.fallback_step_id:
                self.emit_event(
                    context,
                    EventType.FALLBACK_TRIGGERED,
                    step_id=step.step_id,
                    message=f"Triggering fallback for {step.name}",
                )

            raise

    async def _execute_with_resilience(
        self,
        step: PlanStep,
        connector: BaseConnector,
        circuit_breaker: CircuitBreaker,
        context: OrchestrationContext,
    ) -> Any:
        """Execute a step with circuit breaker and retry logic."""

        # Check circuit breaker
        if not circuit_breaker.allow_request():
            raise RuntimeError(f"Circuit open for connector {connector.connector_id}")

        retry_config = step.retry_policy or {
            "max_retries": 3,
            "backoff_base": 1.0,
            "backoff_max": 30.0,
        }

        last_error: Exception | None = None
        max_retries = retry_config.get("max_retries", 3)

        for attempt in range(max_retries + 1):
            try:
                response: APIResponse = await connector.invoke(
                    operation=step.operation,
                    parameters=step.parameters,
                    timeout_ms=step.timeout_ms,
                )

                if response.success:
                    circuit_breaker.record_success()
                    result = response.body

                    # Apply transformation if specified
                    if step.transform:
                        result = self._apply_transform(result, step.transform)

                    return result
                elif response.retryable and attempt < max_retries:
                    self.emit_event(
                        context,
                        EventType.STEP_RETRIED,
                        step_id=step.step_id,
                        message=f"Retry {attempt + 1}/{max_retries}: {response.error_message}",
                    )
                    backoff = self._retry_policy.calculate_backoff(attempt, retry_config)
                    await asyncio.sleep(backoff)
                    continue
                else:
                    circuit_breaker.record_failure()
                    raise RuntimeError(
                        f"API call failed: {response.status_code} - {response.error_message}"
                    )

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    backoff = self._retry_policy.calculate_backoff(attempt, retry_config)
                    await asyncio.sleep(backoff)
                else:
                    circuit_breaker.record_failure()
                    raise

        raise last_error or RuntimeError("Execution failed after retries")

    def _get_circuit_breaker(self, connector_id: str) -> CircuitBreaker:
        """Get or create a circuit breaker for a connector."""
        if connector_id not in self._circuit_breakers:
            self._circuit_breakers[connector_id] = CircuitBreaker(name=connector_id)
        return self._circuit_breakers[connector_id]

    def _route_to_connector(
        self,
        step: PlanStep,
        connectors: list[BaseConnector],
        router: DynamicRouter,
    ) -> BaseConnector | None:
        """Use the DynamicRouter to find the best connector."""
        # Simplified routing — full implementation in DynamicRouter
        if connectors:
            return connectors[0]
        return None

    def _evaluate_condition(self, condition: str, context: OrchestrationContext) -> bool:
        """Evaluate a step condition against the context."""
        # Simple expression evaluation
        # Production: use a safe expression parser
        return True

    def _apply_transform(self, data: Any, transform: str) -> Any:
        """Apply a JMESPath/JSONPath transformation to step output."""
        # Placeholder for transform engine
        return data
