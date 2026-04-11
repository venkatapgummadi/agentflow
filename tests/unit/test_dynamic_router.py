"""
Tests for the DynamicRouter intelligent endpoint selection.

Verifies multi-dimensional scoring, routing strategies, and metrics tracking.

Author: Venkata Pavan Kumar Gummadi
"""

from agentflow.routing.dynamic_router import (
    DynamicRouter,
    RoutingWeights,
    EndpointScore,
)


class TestRoutingWeights:
    """Test weight configuration and presets."""

    def test_default_weights_valid(self):
        w = RoutingWeights()
        assert w.validate()

    def test_balanced_preset(self):
        w = RoutingWeights.balanced()
        assert w.validate()
        assert w.latency == w.cost == w.rate_limit == w.capability == w.health

    def test_low_latency_preset(self):
        w = RoutingWeights.low_latency()
        assert w.validate()
        assert w.latency > w.cost

    def test_low_cost_preset(self):
        w = RoutingWeights.low_cost()
        assert w.validate()
        assert w.cost > w.latency


class TestDynamicRouter:
    """Test dynamic routing logic."""

    def setup_method(self):
        self.router = DynamicRouter(weights=RoutingWeights.balanced())

    def test_returns_none_for_empty_candidates(self):
        result = self.router.route([])
        assert result is None

    def test_returns_single_candidate(self):
        candidates = [{"endpoint_id": "ep1", "tags": ["customer"]}]
        result = self.router.route(candidates)
        assert result["endpoint_id"] == "ep1"

    def test_prefers_lower_latency(self):
        router = DynamicRouter(weights=RoutingWeights.low_latency())
        candidates = [
            {"endpoint_id": "slow", "latency_p95_ms": 500, "tags": []},
            {"endpoint_id": "fast", "latency_p95_ms": 10, "tags": []},
        ]
        result = router.route(candidates)
        assert result["endpoint_id"] == "fast"

    def test_prefers_lower_cost(self):
        router = DynamicRouter(weights=RoutingWeights.low_cost())
        candidates = [
            {"endpoint_id": "expensive", "cost_per_call": 1.0, "tags": []},
            {"endpoint_id": "cheap", "cost_per_call": 0.01, "tags": []},
        ]
        result = router.route(candidates)
        assert result["endpoint_id"] == "cheap"

    def test_capability_matching(self):
        candidates = [
            {"endpoint_id": "ep1", "tags": ["customer", "crm"]},
            {"endpoint_id": "ep2", "tags": ["inventory", "warehouse"]},
        ]
        result = self.router.route(candidates, required_capability="customer")
        assert result["endpoint_id"] == "ep1"

    def test_metrics_tracking(self):
        self.router.record_call_result("ep1", success=True, latency_ms=50)
        self.router.record_call_result("ep1", success=True, latency_ms=100)
        self.router.record_call_result("ep1", success=False)

        metrics = self.router._metrics["ep1"]
        assert metrics.total_calls == 3
        assert metrics.successful_calls == 2
        assert metrics.failed_calls == 1

    def test_score_all_returns_scores(self):
        candidates = [
            {"endpoint_id": "ep1", "tags": ["api"]},
            {"endpoint_id": "ep2", "tags": ["api"]},
        ]
        scores = self.router.score_all(candidates)
        assert len(scores) == 2
        assert all(isinstance(s, EndpointScore) for s in scores)
