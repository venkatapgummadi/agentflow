"""
Smoke tests for the routing-weight ablation harness.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

from experiments.routing_weight_ablation import (
    AblationResult,
    best_n,
    run_ablation,
    summary,
)


def test_ablation_runs_and_returns_results():
    results = run_ablation(requests=20, grid=2, seed=1)
    assert results
    for r in results:
        assert isinstance(r, AblationResult)
        assert 0.0 <= r.selection_accuracy <= 1.0
        assert r.mean_regret >= -1e-9
        assert r.samples == 20


def test_summary_has_expected_keys():
    results = run_ablation(requests=10, grid=2, seed=2)
    s = summary(results)
    expected_keys = (
        "vectors", "accuracy_mean", "accuracy_max",
        "accuracy_min", "regret_mean", "regret_min",
    )
    for k in expected_keys:
        assert k in s


def test_top_vectors_are_sorted():
    results = run_ablation(requests=10, grid=2, seed=3)
    top = best_n(results, 5)
    accs = [r.selection_accuracy for r in top]
    assert accs == sorted(accs, reverse=True)


def test_seed_makes_results_deterministic():
    a = run_ablation(requests=20, grid=2, seed=99)
    b = run_ablation(requests=20, grid=2, seed=99)
    accs_a = [r.selection_accuracy for r in a]
    accs_b = [r.selection_accuracy for r in b]
    assert accs_a == accs_b
