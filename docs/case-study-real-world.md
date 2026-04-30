# Real-world deployment recipe

> **Read this first.** This document does *not* report finished
> production-pilot results. It provides a reproducible recipe for
> running AgentFlow against real public APIs so reviewers and users
> can generate their own measurements. The fabricated pilot numbers
> that appeared in an earlier draft of this document have been
> removed.

## Why this document exists

Reviewers 1, 2, 3 and 4 of  submission #0692 asked for
evaluation beyond simulated connectors. The shortest credible answer
is to give anyone with a Python install a one-command path to
exercise the full `AgentOrchestrator` against real production APIs
and capture latency, throughput and error-rate metrics on their own
hardware. That recipe is below.

## Recipe: public-API benchmark

Script: `examples/real_world_public_apis.py`

**Targets**

| Target | URL | Purpose |
| --- | --- | --- |
| `httpbin_get` | `https://httpbin.org/get` | echo / diagnostic |
| `jsonplaceholder_posts` | `https://jsonplaceholder.typicode.com/posts/1` | fake-but-real REST CRUD |
| `publicapis_entries` | `https://api.publicapis.org/entries?limit=1` | public-API directory |

**Reproduce on your machine**

```bash
pip install -e ".[all]"
python examples/real_world_public_apis.py --workflows 50 --concurrency 10 --json
```

The script emits a JSON record with `throughput_rps`, `p50_ms`,
`p95_ms`, `error_rate`, and the list of upstream targets. Paste the
JSON into a follow-up issue if you want it included in the next
revision of this doc.

## Honest caveats

* **Network-dependent.** The script requires outbound HTTPS to the
  three target domains. In an offline / air-gapped CI environment
  every call fails and `error_rate` correctly reports `1.0` -- which
  is itself a useful resilience-path test.
* **Rate limits.** The targets are free public services. Throughput
  is bounded by their rate limits, not by AgentFlow.
* **No production-pilot numbers in this doc.** The previous draft
  included specific FinTech and HealthTech pilot statistics. Those
  numbers were not measured -- they have been removed pending real
  measurements from a real deployment.

## What to look at instead, today

| If you want | Look at |
| --- | --- |
| Modelled comparison vs. baselines | `docs/baseline-comparison.md` (clearly labelled as a model, not a measurement) |
| Routing-weight sensitivity from real script output | `docs/routing-weights-ablation.md` |
| Parser-quality numbers for rule vs. LLM-backed parsing | `docs/parser-quality.md` and `experiments/parser_quality_benchmark.py` |
| The full unit-test suite exercising every new code path | `pytest -q` |

## Roadmap

* Capture median throughput / latency / error-rate from a 1k-workflow
  run against the public APIs above and embed the result here.
* Recruit one production design partner per vertical and report
  *measured* numbers in the camera-ready revision.
