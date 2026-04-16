"""
Tests for the BudgetRouter — cost-aware routing.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import pytest

from agentflow.routing.budget_router import (
    BudgetExhaustedError,
    BudgetMode,
    BudgetRouter,
)
from agentflow.routing.dynamic_router import RoutingWeights


def _candidates() -> list[dict]:
    return [
        {
            "endpoint_id": "cheap",
            "connector_id": "c1",
            "cost_per_call": 0.001,
            "latency_p95_ms": 200,
            "rate_limit_rpm": 1000,
            "tags": ["customer", "fetch"],
        },
        {
            "endpoint_id": "fast",
            "connector_id": "c2",
            "cost_per_call": 0.05,
            "latency_p95_ms": 50,
            "rate_limit_rpm": 1000,
            "tags": ["customer", "fetch"],
        },
        {
            "endpoint_id": "premium",
            "connector_id": "c3",
            "cost_per_call": 0.5,
            "latency_p95_ms": 30,
            "rate_limit_rpm": 1000,
            "tags": ["customer", "fetch"],
        },
    ]


class TestBudgetState:
    def test_remaining_clamped_at_zero(self):
        router = BudgetRouter(default_budget=1.0)
        state = router.start_context("ctx-1")
        router.charge("ctx-1", 1.5)
        assert state.remaining == 0.0
        assert state.utilization == 1.0

    def test_charge_negative_rejected(self):
        router = BudgetRouter(default_budget=1.0)
        router.start_context("ctx-1")
        with pytest.raises(ValueError):
            router.charge("ctx-1", -0.5)


class TestBudgetRouterFiltering:
    def test_routes_normally_when_within_budget(self):
        router = BudgetRouter(
            default_budget=1.0,
            mode=BudgetMode.HARD_REJECT,
            weights=RoutingWeights.low_latency(),
        )
        router.start_context("ctx-1")
        winner = router.route(
            _candidates(),
            required_capability="customer.fetch",
            context={"context_id": "ctx-1"},
        )
        assert winner is not None
        # low_latency weights should pick the fastest endpoint ("premium")
        # because it's still within budget.
        assert winner["endpoint_id"] in {"premium", "fast"}

    def test_filters_endpoints_above_remaining_budget(self):
        router = BudgetRouter(default_budget=0.10, mode=BudgetMode.HARD_REJECT)
        router.start_context("ctx-1")
        winner = router.route(
            _candidates(),
            context={"context_id": "ctx-1"},
        )
        # premium (0.5) exceeds the 0.10 budget.
        assert winner is not None
        assert winner["endpoint_id"] != "premium"

    def test_hard_reject_when_no_candidate_fits(self):
        router = BudgetRouter(default_budget=0.0001, mode=BudgetMode.HARD_REJECT)
        router.start_context("ctx-1")
        with pytest.raises(BudgetExhaustedError):
            router.route(_candidates(), context={"context_id": "ctx-1"})

    def test_downgrade_picks_cheapest_when_no_candidate_fits(self):
        router = BudgetRouter(default_budget=0.0001, mode=BudgetMode.DOWNGRADE)
        router.start_context("ctx-1")
        winner = router.route(_candidates(), context={"context_id": "ctx-1"})
        assert winner is not None
        assert winner["endpoint_id"] == "cheap"

    def test_downgrade_threshold_prefers_cheap_when_utilization_high(self):
        router = BudgetRouter(
            default_budget=1.0,
            mode=BudgetMode.DOWNGRADE,
            downgrade_threshold=0.5,
            weights=RoutingWeights.low_latency(),
        )
        router.start_context("ctx-1")
        # Push utilization above the downgrade threshold
        router.charge("ctx-1", 0.6)
        winner = router.route(
            _candidates(),
            context={"context_id": "ctx-1"},
        )
        # Despite low_latency weights, downgrade should select "cheap"
        assert winner is not None
        assert winner["endpoint_id"] == "cheap"


class TestBudgetMetrics:
    def test_metrics_reflect_charges(self):
        router = BudgetRouter(default_budget=1.0)
        router.start_context("ctx-1")
        router.charge("ctx-1", 0.25, endpoint_id="x")
        router.charge("ctx-1", 0.10, endpoint_id="y")
        m = router.get_budget_metrics("ctx-1")
        assert m["spent"] == 0.35
        assert m["remaining"] == 0.65
        assert m["calls"] == 2

    def test_route_without_context_id_works_like_dynamic_router(self):
        router = BudgetRouter(default_budget=0.01)
        # No context_id => no budget filtering
        winner = router.route(_candidates())
        assert winner is not None
