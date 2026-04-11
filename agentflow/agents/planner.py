"""
Planner Agent — creates execution plans from intents.

The PlannerAgent analyzes the parsed intent and available APIs to
construct an optimal ExecutionPlan (DAG). It determines:
- Which APIs to call and in what order
- Data dependencies between steps
- Parallelization opportunities
- Fallback strategies for critical steps

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agentflow.agents.base_agent import BaseAgent
from agentflow.core.context import EventType, OrchestrationContext
from agentflow.core.plan import ExecutionPlan, PlanStep, StepType

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    """
    Creates execution plans from parsed intents.

    The planner uses capability matching to find the best APIs
    for each step of the workflow, then builds a DAG with
    maximum parallelism while respecting data dependencies.

    Planning strategy:
    1. Decompose the intent into atomic operations
    2. Match each operation to available API endpoints
    3. Analyze data flow to determine dependencies
    4. Identify parallelization opportunities
    5. Assign fallback chains for critical steps
    """

    def __init__(self, **kwargs: Any):
        super().__init__(name="PlannerAgent", **kwargs)
        self._capability_index: Dict[str, List[Dict[str, Any]]] = {}

    async def execute(self, context: OrchestrationContext, **kwargs: Any) -> ExecutionPlan:
        """Execute planning phase."""
        intent = kwargs.get("intent", context.intent)
        parsed = kwargs.get("parsed_intent", {})
        apis = kwargs.get("available_apis", [])
        return await self.create_plan(intent, parsed, apis)

    async def create_plan(
        self,
        intent: str,
        parsed_intent: Optional[Dict[str, Any]] = None,
        available_apis: Optional[List[Dict[str, Any]]] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> ExecutionPlan:
        """
        Create an execution plan for the given intent.

        Algorithm:
        1. Extract required capabilities from parsed intent
        2. Match capabilities to available APIs using semantic scoring
        3. Build dependency graph based on data flow analysis
        4. Optimize for parallel execution where possible
        5. Attach fallback endpoints for critical paths
        """
        parsed = parsed_intent or {}
        apis = available_apis or []
        params = parameters or {}

        plan = ExecutionPlan(intent=intent)

        # Index available APIs by capability
        self._build_capability_index(apis)

        # Extract operations from parsed intent
        operations = parsed.get("operations", [])
        if not operations:
            operations = self._decompose_intent(intent)

        # Build steps with dependency analysis
        step_map: Dict[str, PlanStep] = {}
        for i, op in enumerate(operations):
            # Find matching APIs
            matched_api = self._match_capability(
                operation=op,
                apis=apis,
            )

            # Determine dependencies
            depends_on = self._analyze_dependencies(
                operation=op,
                previous_steps=step_map,
            )

            step = plan.add_step(
                name=op.get("name", f"step_{i}"),
                step_type=StepType(op.get("type", "api_call")),
                connector_id=matched_api.get("connector_id", "") if matched_api else "",
                operation=op.get("operation", ""),
                parameters={**params, **op.get("parameters", {})},
                depends_on=depends_on,
                transform=op.get("transform"),
                condition=op.get("condition"),
                timeout_ms=op.get("timeout_ms", 30000),
            )
            step_map[step.name] = step

        logger.info(
            "Created plan with %d steps (%d parallelizable) for: %s",
            len(plan.steps),
            self._count_parallelizable(plan),
            intent,
        )

        plan.metadata["parallelizable_steps"] = self._count_parallelizable(plan)
        plan.metadata["critical_path_length"] = self._critical_path_length(plan)

        return plan

    def _build_capability_index(self, apis: List[Dict[str, Any]]) -> None:
        """Index APIs by their tags and capabilities for fast lookup."""
        self._capability_index.clear()
        for api in apis:
            for tag in api.get("tags", []):
                tag_lower = tag.lower()
                if tag_lower not in self._capability_index:
                    self._capability_index[tag_lower] = []
                self._capability_index[tag_lower].append(api)

    def _match_capability(
        self,
        operation: Dict[str, Any],
        apis: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Find the best matching API for an operation.

        Scoring factors:
        - Tag/capability overlap (semantic match)
        - Latency (lower is better)
        - Cost per call (lower is better)
        - Rate limit headroom (higher is better)
        """
        required_tags = set(
            t.lower() for t in operation.get("required_tags", [])
        )

        best_match = None
        best_score = -1.0

        for api in apis:
            api_tags = set(t.lower() for t in api.get("tags", []))
            tag_overlap = len(required_tags & api_tags)

            if tag_overlap == 0 and required_tags:
                continue

            # Multi-dimensional scoring
            tag_score = tag_overlap / max(len(required_tags), 1)
            latency_score = 1.0 / (1.0 + api.get("latency_p95_ms", 100) / 1000)
            cost_score = 1.0 / (1.0 + api.get("cost_per_call", 0))
            headroom_score = min(api.get("rate_limit_rpm", 1000), 1000) / 1000

            total_score = (
                0.4 * tag_score
                + 0.25 * latency_score
                + 0.2 * cost_score
                + 0.15 * headroom_score
            )

            if total_score > best_score:
                best_score = total_score
                best_match = api

        return best_match

    def _analyze_dependencies(
        self,
        operation: Dict[str, Any],
        previous_steps: Dict[str, PlanStep],
    ) -> List[str]:
        """
        Determine which previous steps this operation depends on.

        Analyzes input requirements to find data dependencies.
        """
        deps: List[str] = []
        required_inputs = operation.get("inputs_from", [])

        for input_ref in required_inputs:
            if input_ref in previous_steps:
                deps.append(previous_steps[input_ref].step_id)

        return deps

    def _decompose_intent(self, intent: str) -> List[Dict[str, Any]]:
        """
        Decompose a natural-language intent into atomic operations.

        This is a rule-based fallback; the full NLP pipeline uses
        the IntentParser for richer decomposition.
        """
        # Simple keyword-based decomposition
        operations: List[Dict[str, Any]] = []
        keywords_to_ops = {
            "fetch": "api_call",
            "get": "api_call",
            "create": "api_call",
            "update": "api_call",
            "delete": "api_call",
            "enrich": "transform",
            "validate": "validate",
            "check": "condition",
            "aggregate": "aggregate",
        }

        words = intent.lower().split()
        for word in words:
            if word in keywords_to_ops:
                operations.append({
                    "name": word,
                    "type": keywords_to_ops[word],
                    "operation": word,
                    "parameters": {},
                })

        if not operations:
            operations.append({
                "name": "default_call",
                "type": "api_call",
                "operation": intent,
                "parameters": {},
            })

        return operations

    def _count_parallelizable(self, plan: ExecutionPlan) -> int:
        """Count steps that can run in parallel (no dependencies)."""
        return sum(1 for s in plan.steps if not s.depends_on)

    def _critical_path_length(self, plan: ExecutionPlan) -> int:
        """Calculate the longest dependency chain (critical path)."""
        if not plan.steps:
            return 0

        step_ids = {s.step_id for s in plan.steps}
        memo: Dict[str, int] = {}

        def depth(step: PlanStep) -> int:
            if step.step_id in memo:
                return memo[step.step_id]
            if not step.depends_on:
                memo[step.step_id] = 1
                return 1
            max_dep = 0
            for dep_id in step.depends_on:
                dep_step = plan.get_step(dep_id)
                if dep_step:
                    max_dep = max(max_dep, depth(dep_step))
            memo[step.step_id] = max_dep + 1
            return memo[step.step_id]

        return max(depth(s) for s in plan.steps)
