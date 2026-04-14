"""
BudgetRouter — cost-aware extension of DynamicRouter.

Tracks per-orchestration spend and enforces budget caps. Endpoints
that would push the orchestration over budget are filtered out, and
the router can be configured to either:

- HARD_REJECT: refuse to route when budget is exhausted.
- DOWNGRADE: prefer the cheapest viable candidate when remaining
  budget gets tight.

Pairs with the existing DynamicRouter — all standard scoring
behavior is preserved; budget filtering happens before scoring.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agentflow.routing.dynamic_router import DynamicRouter, RoutingWeights

logger = logging.getLogger(__name__)


class BudgetExhaustedError(Exception):
    """Raised when no candidate can be routed without exceeding budget."""


class BudgetMode(Enum):
    """Behavior when remaining budget cannot fit any candidate."""

    HARD_REJECT = "hard_reject"
    DOWNGRADE = "downgrade"


@dataclass
class BudgetState:
    """Per-context budget tracking state."""

    context_id: str = ""
    budget_total: float = 0.0
    spent: float = 0.0
    call_count: int = 0
    rejected_count: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def remaining(self) -> float:
        return max(0.0, self.budget_total - self.spent)

    @property
    def utilization(self) -> float:
        if self.budget_total <= 0:
            return 0.0
        return min(1.0, self.spent / self.budget_total)


class BudgetRouter(DynamicRouter):
    """
    DynamicRouter subclass that enforces a per-context budget.

    Args:
        default_budget: Default budget (in cost units) per context.
        mode: BudgetMode controlling out-of-budget behavior.
        downgrade_threshold: Utilization (0–1) above which DOWNGRADE
            mode prefers the cheapest viable endpoint regardless of
            other scoring dimensions. Default 0.8.
        weights / custom_scorers: Forwarded to DynamicRouter.

    Usage:
        router = BudgetRouter(
            default_budget=1.00,
            mode=BudgetMode.DOWNGRADE,
            weights=RoutingWeights.balanced(),
        )
        router.start_context("orch-42")
        winner = router.route(candidates, required_capability="customer.fetch",
                              context={"context_id": "orch-42"})
        router.charge("orch-42", winner["cost_per_call"])
    """

    def __init__(
        self,
        default_budget: float = 1.0,
        mode: BudgetMode = BudgetMode.HARD_REJECT,
        downgrade_threshold: float = 0.8,
        weights: RoutingWeights | None = None,
        custom_scorers: dict[str, Callable] | None = None,
    ):
        super().__init__(weights=weights, custom_scorers=custom_scorers)
        if default_budget < 0:
            raise ValueError("default_budget must be >= 0")
        if not 0.0 <= downgrade_threshold <= 1.0:
            raise ValueError("downgrade_threshold must be in [0, 1]")
        self.default_budget = default_budget
        self.mode = mode
        self.downgrade_threshold = downgrade_threshold
        self._budgets: dict[str, BudgetState] = {}

    # ── Budget Lifecycle ──────────────────────────────────────────────

    def start_context(
        self, context_id: str, budget: float | None = None
    ) -> BudgetState:
        """Initialize (or reset) budget tracking for a context."""
        state = BudgetState(
            context_id=context_id,
            budget_total=self.default_budget if budget is None else budget,
        )
        self._budgets[context_id] = state
        return state

    def get_state(self, context_id: str) -> BudgetState:
        """Get (or lazily create) the BudgetState for a context."""
        if context_id not in self._budgets:
            self.start_context(context_id)
        return self._budgets[context_id]

    def charge(
        self,
        context_id: str,
        amount: float,
        endpoint_id: str = "",
    ) -> BudgetState:
        """Record a spend against a context's budget."""
        state = self.get_state(context_id)
        if amount < 0:
            raise ValueError("amount must be >= 0")
        state.spent += amount
        state.call_count += 1
        state.history.append(
            {"endpoint_id": endpoint_id, "amount": amount, "spent": state.spent}
        )
        return state

    # ── Routing Override ──────────────────────────────────────────────

    def route(  # type: ignore[override]
        self,
        candidates: list[dict[str, Any]],
        required_capability: str = "",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Budget-aware route. Adds two phases on top of DynamicRouter:

        1. Filter candidates by remaining budget.
        2. In DOWNGRADE mode, when utilization >= downgrade_threshold,
           pick the cheapest viable candidate directly.
        """
        ctx_id = (context or {}).get("context_id", "")
        if not ctx_id:
            # No context_id supplied — fall back to plain routing.
            return super().route(candidates, required_capability, context)

        state = self.get_state(ctx_id)
        viable = [
            c for c in candidates
            if float(c.get("cost_per_call", 0.0)) <= state.remaining
        ]

        if not viable:
            state.rejected_count += 1
            logger.warning(
                "BudgetRouter: no viable candidate for context %s "
                "(remaining=%.4f, spent=%.4f/%.4f)",
                ctx_id,
                state.remaining,
                state.spent,
                state.budget_total,
            )
            if self.mode == BudgetMode.HARD_REJECT:
                raise BudgetExhaustedError(
                    f"No candidate fits remaining budget {state.remaining:.4f} "
                    f"for context {ctx_id}"
                )
            # DOWNGRADE with no viable candidates: cheapest overall.
            return min(
                candidates,
                key=lambda c: float(c.get("cost_per_call", 0.0)),
                default=None,
            )

        if (
            self.mode == BudgetMode.DOWNGRADE
            and state.utilization >= self.downgrade_threshold
        ):
            cheapest = min(
                viable, key=lambda c: float(c.get("cost_per_call", 0.0))
            )
            logger.info(
                "BudgetRouter DOWNGRADE active for %s (util=%.2f): "
                "selected cheapest endpoint %s",
                ctx_id,
                state.utilization,
                cheapest.get("endpoint_id", ""),
            )
            return cheapest

        return super().route(viable, required_capability, context)

    def get_budget_metrics(self, context_id: str) -> dict[str, Any]:
        """Snapshot of budget consumption for one context."""
        state = self.get_state(context_id)
        return {
            "context_id": state.context_id,
            "budget_total": state.budget_total,
            "spent": round(state.spent, 6),
            "remaining": round(state.remaining, 6),
            "utilization": round(state.utilization, 4),
            "calls": state.call_count,
            "rejections": state.rejected_count,
        }
