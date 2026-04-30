"""
Routing-weight ablation experiment.

Reviewer 3 noted that the routing weight configuration "lacks deeper
empirical validation". This script sweeps the five-dimensional weight
vector (l, c, r, k, h) over a synthetic-but-realistic candidate
population and reports decision quality across multiple metrics:

* **selection_accuracy** — frequency that the router picks the same
  endpoint as a brute-force *oracle* that minimises a target
  utility function;
* **mean_regret** — average difference between the oracle's utility
  and the router's selection (lower = better);
* **diversity** — fraction of unique endpoints chosen across requests
  (a sanity check that the router is not collapsing to a single pick).

The candidate population mirrors the four enterprise verticals used
in the paper (FinTech, HealthTech, E-Commerce, Insurance) so the
sensitivity surface aligns with the rest of the evaluation.

Usage::

    python -m experiments.routing_weight_ablation
    python -m experiments.routing_weight_ablation --requests 5000 --grid 5

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import random
import statistics
from dataclasses import dataclass
from typing import Any

from agentflow.routing.dynamic_router import DynamicRouter, RoutingWeights

logger = logging.getLogger(__name__)


VERTICALS = ("fintech", "healthtech", "ecommerce", "insurance")


@dataclass
class AblationResult:
    weights: tuple[float, float, float, float, float]
    selection_accuracy: float
    mean_regret: float
    diversity: float
    samples: int

    def as_row(self) -> dict[str, Any]:
        lat, cost, rate, cap, health = self.weights
        return {
            "latency": lat,
            "cost": cost,
            "rate_limit": rate,
            "capability": cap,
            "health": health,
            "selection_accuracy": round(self.selection_accuracy, 4),
            "mean_regret": round(self.mean_regret, 4),
            "diversity": round(self.diversity, 4),
            "samples": self.samples,
        }


def _make_population(rng: random.Random, n: int = 12) -> list[dict[str, Any]]:
    pop = []
    for i in range(n):
        vertical = rng.choice(VERTICALS)
        pop.append(
            {
                "endpoint_id": f"ep_{vertical}_{i}",
                "latency_p95_ms": rng.uniform(20, 600),
                "cost_per_call": rng.uniform(0.0, 0.05),
                "rate_limit_rpm": rng.choice([60, 200, 600, 2000, 10000]),
                "tags": [vertical, rng.choice(["customer", "order", "payment", "credit"])],
                "health_score": rng.uniform(0.5, 1.0),
            }
        )
    return pop


def _oracle_utility(candidate: dict[str, Any]) -> float:
    """A neutral 'true' utility used to grade the router's choices."""
    latency = candidate["latency_p95_ms"]
    cost = candidate["cost_per_call"]
    rpm = candidate["rate_limit_rpm"]
    health = candidate.get("health_score", 1.0)
    # lower latency, lower cost, higher rpm, higher health => higher utility
    return health * (1.0 / (1.0 + latency / 200)) * (1.0 / (1.0 + cost * 50)) * (rpm / 10000)


def _enumerate_weights(grid: int) -> list[tuple[float, float, float, float, float]]:
    """All 5-tuples on a `grid`-sized simplex that sum to 1."""
    points = [i / grid for i in range(grid + 1)]
    out: list[tuple[float, float, float, float, float]] = []
    for combo in itertools.product(points, repeat=5):
        if abs(sum(combo) - 1.0) < 1e-6:
            out.append(combo)  # type: ignore[arg-type]
    return out


def run_ablation(
    requests: int = 1000,
    grid: int = 4,
    seed: int = 42,
) -> list[AblationResult]:
    rng = random.Random(seed)
    population = _make_population(rng)
    weight_vectors = _enumerate_weights(grid)
    logger.info(
        "Ablation over %d weight vectors x %d requests = %d evaluations",
        len(weight_vectors),
        requests,
        len(weight_vectors) * requests,
    )

    # Pre-pick the request stream so every weight vector sees the same workload.
    workload = [
        (rng.choice(VERTICALS), rng.sample(population, k=min(6, len(population))))
        for _ in range(requests)
    ]

    results: list[AblationResult] = []
    for weights_tuple in weight_vectors:
        lat, cost, rate, cap, health = weights_tuple
        router = DynamicRouter(
            weights=RoutingWeights(
                latency=lat, cost=cost, rate_limit=rate, capability=cap, health=health,
            )
        )
        hits = 0
        regrets: list[float] = []
        chosen_ids: list[str] = []
        for vertical, candidates in workload:
            picked = router.route(candidates, required_capability=vertical)
            oracle = max(candidates, key=_oracle_utility)
            if picked is None:
                continue
            chosen_ids.append(picked["endpoint_id"])
            if picked["endpoint_id"] == oracle["endpoint_id"]:
                hits += 1
            regrets.append(_oracle_utility(oracle) - _oracle_utility(picked))
        results.append(
            AblationResult(
                weights=weights_tuple,
                selection_accuracy=hits / len(workload),
                mean_regret=statistics.fmean(regrets) if regrets else 0.0,
                diversity=len(set(chosen_ids)) / max(len(chosen_ids), 1),
                samples=len(workload),
            )
        )
    return results


def best_n(results: list[AblationResult], n: int = 5) -> list[AblationResult]:
    return sorted(results, key=lambda r: (-r.selection_accuracy, r.mean_regret))[:n]


def summary(results: list[AblationResult]) -> dict[str, Any]:
    accs = [r.selection_accuracy for r in results]
    regrets = [r.mean_regret for r in results]
    return {
        "vectors": len(results),
        "accuracy_mean": round(statistics.fmean(accs), 4),
        "accuracy_max": round(max(accs), 4),
        "accuracy_min": round(min(accs), 4),
        "regret_mean": round(statistics.fmean(regrets), 4),
        "regret_min": round(min(regrets), 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--grid", type=int, default=4, help="simplex grid resolution")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    results = run_ablation(requests=args.requests, grid=args.grid, seed=args.seed)
    payload = {
        "summary": summary(results),
        "top_vectors": [r.as_row() for r in best_n(results, args.top)],
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        s = payload["summary"]
        print(f"Evaluated {s['vectors']} weight vectors over {results[0].samples} requests")
        print(
            "  accuracy:"
            f" mean={s['accuracy_mean']}  max={s['accuracy_max']}  min={s['accuracy_min']}"
        )
        print(f"  regret:   mean={s['regret_mean']}    min={s['regret_min']}")
        print()
        print(f"Top {args.top} weight vectors (latency, cost, rate, capability, health):")
        for row in payload["top_vectors"]:
            print(
                f"  ({row['latency']:.2f}, {row['cost']:.2f}, {row['rate_limit']:.2f}, "
                f"{row['capability']:.2f}, {row['health']:.2f}) "
                f"acc={row['selection_accuracy']}  regret={row['mean_regret']}"
            )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
