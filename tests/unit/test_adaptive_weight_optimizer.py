"""
Unit tests for AdaptiveWeightOptimizer.

Tests: weight initialization, EMA tracking, SLA violation detection,
weight adjustment with momentum, composite scoring, reset behavior.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import time

from agentflow.routing.adaptive_weight_optimizer import (
    AdaptiveWeightOptimizer,
    DimensionSLA,
    EndpointPerformanceSnapshot,
    RoutingDimension,
)


def _make_snapshot(
    endpoint: str = "api-v1",
    latency: float = 100.0,
    cost: float = 0.01,
    headroom: float = 0.5,
    capability: float = 0.9,
    health: float = 1.0,
) -> EndpointPerformanceSnapshot:
    return EndpointPerformanceSnapshot(
        endpoint_id=endpoint,
        timestamp=time.time(),
        latency_ms=latency,
        cost_per_call=cost,
        rate_limit_remaining_pct=headroom,
        capability_score=capability,
        health_score=health,
    )


class TestWeightInitialization:
    def test_default_weights_sum_to_one(self) -> None:
        opt = AdaptiveWeightOptimizer()
        assert abs(sum(opt.get_current_weights().values()) - 1.0) < 1e-9

    def test_all_dimensions_present(self) -> None:
        opt = AdaptiveWeightOptimizer()
        for dim in RoutingDimension:
            assert dim in opt.get_current_weights()

    def test_custom_weights(self) -> None:
        custom = {
            RoutingDimension.LATENCY: 0.50,
            RoutingDimension.COST: 0.10,
            RoutingDimension.RATE_LIMIT_HEADROOM: 0.10,
            RoutingDimension.CAPABILITY_MATCH: 0.20,
            RoutingDimension.HEALTH_STATUS: 0.10,
        }
        opt = AdaptiveWeightOptimizer(initial_weights=custom)
        assert opt.get_current_weights()[RoutingDimension.LATENCY] == 0.50

    def test_weight_state_serialization(self) -> None:
        opt = AdaptiveWeightOptimizer()
        state = opt.get_weight_state()
        d = state.to_dict()
        assert "weights" in d
        assert "adjustment_count" in d


class TestEMATracking:
    def test_first_observation_initializes_ema(self) -> None:
        opt = AdaptiveWeightOptimizer(adjustment_interval_seconds=9999)
        opt.observe(_make_snapshot(latency=120.0))
        assert opt._ema_scores["api-v1"][RoutingDimension.LATENCY] == 120.0

    def test_ema_smooths_values(self) -> None:
        opt = AdaptiveWeightOptimizer(ema_decay=0.5, adjustment_interval_seconds=9999)
        opt.observe(_make_snapshot(latency=100.0))
        opt.observe(_make_snapshot(latency=200.0))
        ema = opt._ema_scores["api-v1"][RoutingDimension.LATENCY]
        assert abs(ema - 150.0) < 1e-9

    def test_endpoints_tracked_independently(self) -> None:
        opt = AdaptiveWeightOptimizer(adjustment_interval_seconds=9999)
        opt.observe(_make_snapshot(endpoint="ep-1", latency=50.0))
        opt.observe(_make_snapshot(endpoint="ep-2", latency=200.0))
        assert opt._ema_scores["ep-1"][RoutingDimension.LATENCY] == 50.0
        assert opt._ema_scores["ep-2"][RoutingDimension.LATENCY] == 200.0


class TestSLAViolations:
    def test_latency_violation(self) -> None:
        sla = {RoutingDimension.LATENCY: DimensionSLA(RoutingDimension.LATENCY, 100.0, 0.1)}
        opt = AdaptiveWeightOptimizer(sla_config=sla, adjustment_interval_seconds=9999)
        opt.observe(_make_snapshot(latency=150.0))
        violations = opt._detect_violations()
        assert RoutingDimension.LATENCY in violations

    def test_no_violation_within_tolerance(self) -> None:
        sla = {RoutingDimension.LATENCY: DimensionSLA(RoutingDimension.LATENCY, 100.0, 0.2)}
        opt = AdaptiveWeightOptimizer(sla_config=sla, adjustment_interval_seconds=9999)
        opt.observe(_make_snapshot(latency=110.0))
        violations = opt._detect_violations()
        assert RoutingDimension.LATENCY not in violations

    def test_health_violation(self) -> None:
        dim_sla = DimensionSLA(RoutingDimension.HEALTH_STATUS, 0.95, 0.05)
        sla = {RoutingDimension.HEALTH_STATUS: dim_sla}
        opt = AdaptiveWeightOptimizer(sla_config=sla, adjustment_interval_seconds=9999)
        opt.observe(_make_snapshot(health=0.70))
        violations = opt._detect_violations()
        assert RoutingDimension.HEALTH_STATUS in violations


class TestWeightOptimization:
    def test_violated_dimension_weight_increases(self) -> None:
        dim_sla = DimensionSLA(RoutingDimension.LATENCY, 50.0, 0.1)
        sla = {RoutingDimension.LATENCY: dim_sla}
        opt = AdaptiveWeightOptimizer(
            sla_config=sla, learning_rate=0.1, adjustment_interval_seconds=0
        )
        initial = opt.get_current_weights()[RoutingDimension.LATENCY]
        for _ in range(5):
            opt.observe(_make_snapshot(latency=200.0))
        assert opt.get_current_weights()[RoutingDimension.LATENCY] > initial

    def test_weights_stay_normalized(self) -> None:
        sla = {RoutingDimension.LATENCY: DimensionSLA(RoutingDimension.LATENCY, 50.0)}
        opt = AdaptiveWeightOptimizer(sla_config=sla, adjustment_interval_seconds=0)
        for _ in range(10):
            opt.observe(_make_snapshot(latency=500.0))
        assert abs(sum(opt.get_current_weights().values()) - 1.0) < 1e-9


class TestCompositeScore:
    def test_perfect_scores(self) -> None:
        opt = AdaptiveWeightOptimizer()
        assert abs(opt.compute_composite_score(1, 1, 1, 1, 1) - 1.0) < 1e-9

    def test_zero_scores(self) -> None:
        opt = AdaptiveWeightOptimizer()
        assert abs(opt.compute_composite_score(0, 0, 0, 0, 0)) < 1e-9

    def test_weights_tuple_output(self) -> None:
        opt = AdaptiveWeightOptimizer()
        t = opt.get_weights_as_tuple()
        assert len(t) == 5
        assert abs(sum(t) - 1.0) < 1e-9


class TestReset:
    def test_reset_restores_defaults(self) -> None:
        opt = AdaptiveWeightOptimizer(adjustment_interval_seconds=0)
        opt._sla_config = {RoutingDimension.LATENCY: DimensionSLA(RoutingDimension.LATENCY, 50.0)}
        for _ in range(5):
            opt.observe(_make_snapshot(latency=500.0))
        opt.reset()
        assert opt.get_current_weights() == AdaptiveWeightOptimizer.DEFAULT_WEIGHTS
        assert opt.get_weight_state().adjustment_count == 0


class TestBatchObservation:
    def test_batch_processes_all(self) -> None:
        opt = AdaptiveWeightOptimizer(adjustment_interval_seconds=9999)
        snapshots = [_make_snapshot(endpoint=f"ep-{i}") for i in range(5)]
        opt.observe_batch(snapshots)
        assert len(opt._ema_scores) == 5
