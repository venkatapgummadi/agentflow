# Modelled Comparison vs. Industry Baselines

> **Read this first.** The numbers in this document come from
> `benchmarks/baseline_comparison.py`, which uses **calibrated
> `asyncio.sleep` adapters** to model each system's scheduling cost.
> No real LangChain / MuleSoft / Apache Camel / DataWeave instance is
> invoked. Treat the table below as an *order-of-magnitude*
> sanity check, not an empirical benchmark. A real, fully-instrumented
> head-to-head against installed baselines is on the roadmap.

## What this document does claim

* Documents the *assumptions* behind AgentFlow's relative-throughput
  story (per-step overhead, scheduling model, memory footprint).
* Lets a reviewer probe those assumptions by overriding the
  calibration table with `--calibration my_numbers.json`.

## What this document does *not* claim

* It does not measure real LangChain etc. throughput on your
  hardware. For that, install the baseline and re-run with measured
  per-step cost.
* It does not replace `examples/real_world_public_apis.py`, which
  exercises the actual `AgentOrchestrator` against real HTTP APIs.

## How the model is calibrated

Per-step overhead and steady-state memory come from the calibration
dict in `benchmarks/baseline_comparison.py`. The published values
are an opening estimate, deliberately conservative for AgentFlow:

| Framework      | per_step_ms | scheduling             | memory_mb |
| --- | --- | --- | --- |
| agentflow      | 0.18        | work-stealing          | 48       |
| langchain      | 0.34        | sequential             | 142       |
| apache_camel   | 0.62        | thread-per-route       | 312       |
| mulesoft       | 0.48        | fixed-worker           | 268       |
| dataweave      | 0.21        | transform-only         | 96       |


## Reproduce

```bash
python -m benchmarks.baseline_comparison \
    --workflows 200 --concurrency 50 --steps 8
```

## Modelled results (workflows=200, concurrency=50, steps=8)

| Framework      | Throughput (rps) | P50 ms | P95 ms | Memory (MB) | AgentFlow speedup |
| --- | --- | --- | --- | --- | --- |
| agentflow      | 42870.7          | 0.40   | 1.10   | 48          | 1.00x             |
| mulesoft       | 21060.7          | 1.66   | 2.13   | 268         | 2.04x             |
| dataweave      | 16526.3          | 2.61   | 2.75   | 96          | 2.59x             |
| langchain      | 12063.0          | 3.61   | 4.17   | 142         | 3.55x             |
| apache_camel   | 6085.4           | 7.77   | 7.87   | 312         | 7.04x             |


Numbers are stable across runs of the model to within a few percent
because the harness drives the scheduler to its asymptotic behavior;
real-world measurements vary much more.

## Dimensions beyond throughput

These are qualitative and not produced by the script.

| Dimension | AgentFlow | LangChain | MuleSoft | Apache Camel | DataWeave |
| --- | --- | --- | --- | --- | --- |
| Scheduling model | work-stealing (Kahn) | sequential | fixed worker pool | thread-per-route | transform-only |
| Adaptive circuit breaker | yes | no | partial | partial | n/a |
| Five-dimensional routing | yes | no | no | no | n/a |
| LLM-pluggable intent parsing | yes (v1.1+) | yes | no | no | n/a |
| First-class MuleSoft connector | yes | partial | n/a | yes | yes |
| Compliance-friendly determinism | yes (rule fallback) | partial | yes | yes | yes |

## Why this still answers the reviews

* The harness is now explicit about what it models vs. measures, so
  reviewers can criticise the *calibration*, not the methodology.
* The `--calibration` override means a reviewer who disagrees with
  the per-step overhead estimates can swap in their own measurements
  and re-run in seconds.
* For a real (small-scale) measurement, see
  `docs/case-study-real-world.md` and `examples/real_world_public_apis.py`.
