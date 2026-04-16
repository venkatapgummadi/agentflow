"""
Agent Orchestrator — the central coordination engine.

The AgentOrchestrator manages the lifecycle of an API orchestration:
1. Receives a natural-language intent or structured request
2. Delegates to the PlannerAgent to build an ExecutionPlan
3. Hands the plan to the ExecutorAgent for parallel execution
4. Validates results through the ValidatorAgent
5. Returns aggregated results with full audit trail

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import logging
from typing import Any

from agentflow.agents.executor import ExecutorAgent
from agentflow.agents.planner import PlannerAgent
from agentflow.agents.validator import ValidatorAgent
from agentflow.connectors.base import BaseConnector
from agentflow.core.context import EventType, OrchestrationContext
from agentflow.core.plan import ExecutionPlan
from agentflow.nlp.intent_parser import IntentParser
from agentflow.routing.dynamic_router import DynamicRouter

logger = logging.getLogger(__name__)


class OrchestrationResult:
    """Encapsulates the full result of an orchestration run."""

    def __init__(
        self,
        context: OrchestrationContext,
        plan: ExecutionPlan,
        outputs: dict[str, Any],
        validation: dict[str, Any] | None = None,
    ):
        self.context = context
        self.plan = plan
        self.outputs = outputs
        self.validation = validation
        self.success = plan.is_complete and not plan.has_failures

    @property
    def duration(self) -> float:
        return self.context.duration

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "duration_seconds": round(self.duration, 3),
            "outputs": self.outputs,
            "plan": self.plan.to_dict(),
            "validation": self.validation,
            "audit_summary": self.context.summary(),
        }


class AgentOrchestrator:
    """
    Central engine for AI-powered API orchestration.

    Coordinates multiple specialized agents (Planner, Executor, Validator)
    to transform high-level intents into executed API workflows.

    Usage:
        orchestrator = AgentOrchestrator(
            connectors=[MuleSoftConnector(...), RestConnector(...)],
        )
        result = await orchestrator.execute(
            "Fetch customer 123 and enrich with credit data"
        )
    """

    def __init__(
        self,
        connectors: list[BaseConnector] | None = None,
        router: DynamicRouter | None = None,
        planner: PlannerAgent | None = None,
        executor: ExecutorAgent | None = None,
        validator: ValidatorAgent | None = None,
        intent_parser: IntentParser | None = None,
        max_parallel_steps: int = 10,
        default_timeout_ms: int = 30000,
    ):
        self.connectors: dict[str, BaseConnector] = {}
        for conn in connectors or []:
            self.connectors[conn.connector_id] = conn

        self.router = router or DynamicRouter()
        self.planner = planner or PlannerAgent()
        self.executor = executor or ExecutorAgent()
        self.validator = validator or ValidatorAgent()
        self.intent_parser = intent_parser or IntentParser()
        self.max_parallel_steps = max_parallel_steps
        self.default_timeout_ms = default_timeout_ms

        logger.info(
            "AgentOrchestrator initialized with %d connectors",
            len(self.connectors),
        )

    def register_connector(self, connector: BaseConnector) -> None:
        """Register an additional API connector at runtime."""
        self.connectors[connector.connector_id] = connector
        logger.info("Registered connector: %s", connector.connector_id)

    def discover_apis(self) -> list[dict[str, Any]]:
        """Discover all available APIs across registered connectors."""
        apis: list[dict[str, Any]] = []
        for connector in self.connectors.values():
            try:
                discovered = connector.discover()
                apis.extend(discovered)
            except Exception as e:
                logger.warning(
                    "Discovery failed for %s: %s",
                    connector.connector_id,
                    str(e),
                )
        return apis

    async def execute(
        self,
        intent: str,
        parameters: dict[str, Any] | None = None,
        validate: bool = True,
    ) -> OrchestrationResult:
        """
        Execute a full orchestration from natural-language intent.

        Pipeline:
        1. Parse intent into structured API requirements
        2. Discover available APIs across connectors
        3. Plan an execution DAG
        4. Execute steps with intelligent routing
        5. Validate results

        Args:
            intent: Natural language description of the desired workflow.
            parameters: Additional context parameters.
            validate: Whether to run the ValidatorAgent on results.

        Returns:
            OrchestrationResult with outputs, plan, and audit trail.
        """
        context = OrchestrationContext(intent=intent, metadata=parameters or {})

        logger.info(
            "Starting orchestration %s: %s",
            context.orchestration_id,
            intent,
        )

        # Phase 1: Parse intent
        parsed_intent = self.intent_parser.parse(intent)
        await context.set("intent_parser", "parsed", parsed_intent)

        # Phase 2: Discover APIs
        available_apis = self.discover_apis()
        await context.set("discovery", "available_apis", available_apis)

        # Phase 3: Create execution plan
        context.record_event(
            EventType.PLAN_CREATED,
            agent_id="planner",
            message=f"Planning for intent: {intent}",
        )
        plan = await self.planner.create_plan(
            intent=intent,
            parsed_intent=parsed_intent,
            available_apis=available_apis,
            parameters=parameters or {},
        )

        # Phase 4: Execute the plan
        outputs = await self.executor.execute_plan(
            plan=plan,
            context=context,
            connectors=self.connectors,
            router=self.router,
            max_parallel=self.max_parallel_steps,
        )

        # Phase 5: Validate results
        validation = None
        if validate:
            validation = await self.validator.validate(
                plan=plan,
                context=context,
                outputs=outputs,
            )

        result = OrchestrationResult(
            context=context,
            plan=plan,
            outputs=outputs,
            validation=validation,
        )

        logger.info(
            "Orchestration %s completed in %.2fs — success=%s",
            context.orchestration_id,
            result.duration,
            result.success,
        )
        return result

    async def execute_plan_directly(
        self,
        plan: ExecutionPlan,
    ) -> OrchestrationResult:
        """Execute a pre-built plan without intent parsing."""
        context = OrchestrationContext(intent=plan.intent)

        outputs = await self.executor.execute_plan(
            plan=plan,
            context=context,
            connectors=self.connectors,
            router=self.router,
            max_parallel=self.max_parallel_steps,
        )

        return OrchestrationResult(
            context=context,
            plan=plan,
            outputs=outputs,
        )
