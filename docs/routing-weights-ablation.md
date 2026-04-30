# Routing-Weight Ablation Results

> **Why this document exists.** Reviewer 3 asked for empirical
> validation of the five-dimensional routing weights `(l, c, r, k, h)`.
>
> **All numbers in this document are produced by running
> `experiments/routing_weight_ablation.py` with the configuration
> shown below.** They are not hand-edited.

## Methodology

Script: `experiments/routing_weight_ablation.py`

The script enumerates all weight 5-tuples on a `--grid`-resolution
simplex (default `--grid 4` -> 70 vectors), then runs each
against a fixed pseudo-random workload of `--requests` requests
(default 1000) sampled from the same four verticals used in the
paper (FinTech, HealthTech, E-Commerce, Insurance). For every
request we compare the router's pick against a brute-force *oracle*
that maximises a known utility function over latency, cost,
rate-limit headroom and health.

Three quality metrics are reported:

* `selection_accuracy` -- frequency of matching the oracle's choice.
* `mean_regret` -- expected utility loss vs. the oracle.
* `diversity` -- fraction of unique endpoints chosen across requests.

Caveat: the workload uses the *same* utility function as the oracle,
so this measures *internal consistency* of the router under each
weight vector, not external ground-truth quality. Real-world
calibration would require labelled traffic, which is on the roadmap
(see `docs/case-study-real-world.md`).

## Reproduce

```bash
python -m experiments.routing_weight_ablation \
    --requests 1000 --grid 4 --seed 42 --top 5
```

## Headline summary (requests=1000, grid=4, seed=42)

* Vectors evaluated: **70**
* Selection-accuracy mean: **0.3709**
* Selection-accuracy max:  **0.993**
* Selection-accuracy min:  **0.014**
* Regret mean: **0.1379**
* Regret min:  **0.0**

## Top 5 weight vectors

| (l,    c,    r,    k,    h)        | accuracy | regret  | diversity |
| --- | --- | --- | --- |
| (0.25, 0.00, 0.50, 0.00, 0.25) | 0.993    | 0.0000  | 0.006     |
| (0.25, 0.00, 0.75, 0.00, 0.00) | 0.993    | 0.0000  | 0.006     |
| (0.00, 0.25, 0.50, 0.00, 0.25) | 0.950    | 0.0004  | 0.006     |
| (0.00, 0.25, 0.75, 0.00, 0.00) | 0.950    | 0.0004  | 0.006     |
| (0.25, 0.00, 0.25, 0.00, 0.50) | 0.928    | 0.0037  | 0.007     |


## Observations

1. The best-performing vectors all concentrate weight on a small
   subset of dimensions (typically latency + rate-limit + health). On
   this synthetic workload there is no pressure for an even split.
2. The variance between the best and worst vector
   (0.993 vs. 0.014) shows the
   weight choice is not a free parameter -- defaults matter.
3. The library default `RoutingWeights()` -- `(0.3, 0.2, 0.15, 0.25, 0.1)` -- is not on this grid; rerun with a finer `--grid` to evaluate it directly.

The full surface is available with `--json`:

```bash
python -m experiments.routing_weight_ablation \
    --requests 1000 --grid 4 --seed 42 --top 70 --json > ablation.json
```
