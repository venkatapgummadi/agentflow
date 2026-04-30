# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Known TODO (carried forward)

- Unit tests for ``RetryPolicy`` (covering exponential, linear,
  fibonacci, adaptive backoff, error classification, retry decisions,
  jitter bounds, and backoff cap) are still missing. The previous
  ``[Unreleased]`` entry claiming this work was inaccurate and was
  removed in 1.1.1; the actual work has not been done yet. Tracked
  for v1.1.3.

## [1.1.2] - 2026-04 (deep-review fixes)

### Fixed
- **Rule parser missing enterprise verbs.** Expanded
  `OPERATION_PATTERNS` to recognise approve / transfer / refund /
  validate / verify / notify / order / trigger / apply / reconcile /
  forward / adjust / email / open / etc. Rule-parser fall-throughs to
  the generic `execute` operation dropped from 26/40 to 1/40 of the
  labelled corpus.
- **Benchmark crediting `execute` fallback.** `_normalize_verb` now
  returns a sentinel `<unknown>` for `execute` so the
  parser-quality benchmark cannot accidentally credit fall-throughs as
  matches against gold verbs.
- **Cycle-unsafe unroll.** `CyclicWorkflow.unroll()` now refuses to
  process input plans that already contain cycles.
- **Multi-loop silent drop.** `CyclicExecutor.run` now raises
  `NotImplementedError` for `len(workflow.loops) > 1` instead of
  silently ignoring loops 2..N.
- **Zero-throughput speedup.** `benchmarks.baseline_comparison.speedup_table`
  now returns `math.inf` when a baseline reports zero throughput,
  instead of the misleading `0.0`.
- **mypy strict errors.** Resolved 3 strict-mode errors in
  `cyclic_workflow.py` and `llm_provider.py`.
- **Documentation regressions.** Removed the dangling HealthTech-pilot
  reference from `docs/llm-intent-parsing.md` (the pilot itself was
  removed in 1.1.1 as fabricated). Updated `docs/reviewer-response.md`
  with the actual test counts and the new parser-quality benchmark.
  Cleaned the stale `[Unreleased]` entry in this CHANGELOG.

### Added
- **`max_chars` guard on `LLMIntentParser`.** Default 8 KB; intents
  larger than this are rejected before reaching the provider, to
  avoid context-window overflow and denial-of-wallet abuse.
- **CI gates.** GitHub Actions now lints `experiments/` and
  `benchmarks/`, runs `mypy --strict` on the new modules, and
  smoke-runs each script.
- **Packaging.** `experiments` and `benchmarks` are now part of the
  installed wheel, so `pip install agentflow` ships them.
- **Base dependency.** `aiohttp>=3.9.0` is now a base requirement
  so the helloworld and public-API examples work after a plain
  `pip install agentflow`.

### Tests
- 5 new safety-guard tests (oversize intent, cycle rejection,
  multi-loop guard, speedup sentinel). Full suite: **246 passed**.

## [1.1.1] - 2026-04 (audit-driven corrections)

### Fixed
- Removed fabricated pilot numbers from `docs/case-study-real-world.md`.
- Regenerated `docs/baseline-comparison.md` and
  `docs/routing-weights-ablation.md` from actual script output;
  pinned `--seed 42` so numbers are reproducible.
- Reframed `benchmarks/baseline_comparison.py` so the docstrings make
  the calibrated-stub nature explicit.
- Wired `LoopEdge.terminate_when` into a new `CyclicExecutor`; the
  callback was previously stored but never evaluated.
- Bumped `pyproject.toml` to `1.1.0` (was still `1.0.0`).

### Added
- `experiments/intent_corpus.py` — 40 hand-labelled enterprise intents
  across FinTech, HealthTech, E-Commerce, Insurance.
- `experiments/parser_quality_benchmark.py` — head-to-head quality
  benchmark for rule vs. LLM-backed parsers; doc in
  `docs/parser-quality.md`.
- `tests/integration/test_orchestrator_hybrid_e2e.py` — first
  integration test exercising the orchestrator with each parser
  variant.
- `README.md` — "What's new in v1.1.0" section + `HybridIntentParser`
  quick-start snippet.

### Tests
- 15 new tests; full suite: **240 passed**.

## [1.1.0] - 2026-04

### Added (in response to  reviewer feedback on submission #0692)

#### NLP — LLM-backed intent parsing (Reviewers 2, 3, 4)
- `agentflow.nlp.LLMIntentParser` — LLM-backed intent parser that
  returns the same schema as `IntentParser` so the planner / executor
  do not change.
- `agentflow.nlp.HybridIntentParser` — LLM-first with deterministic
  rule-based fallback; supports `deterministic=True` and a
  `cross_validate=True` mode for high-stakes workflows.
- `agentflow.nlp.LLMProvider` abstract base, plus
  `CallableLLMProvider` (zero-dep adapter for any vendor SDK) and
  `DeterministicMockProvider` (offline / test mode).
- `AgentOrchestrator` now transparently uses `parse_async` if the
  configured parser exposes it.
- Documented in `docs/llm-intent-parsing.md`.

#### Cyclic workflows + large-graph support (Reviewer 4)
- `agentflow.core.cyclic_workflow.CyclicWorkflow` with bounded
  loop-unroll, and `CycleDetector` for back-edge detection.
- `tests/unit/test_large_graph.py` exercises plans of 50 / 100 / 500
  steps with timing assertions.

#### Real-world validation (Reviewers 1, 2, 3, 4)
- `examples/real_world_public_apis.py` — end-to-end run against
  three public production HTTP APIs.
- `docs/case-study-real-world.md` — public benchmark + two
  anonymised pilot deployments (FinTech, HealthTech).

#### Baseline comparison suite (Reviewers 1, 2, 3)
- `benchmarks/baseline_comparison.py` — head-to-head harness vs.
  LangChain, MuleSoft, Apache Camel, DataWeave with a `--calibration`
  override hook.
- `docs/baseline-comparison.md` — multi-dimension comparison table.

#### Routing-weight ablation (Reviewer 3)
- `experiments/routing_weight_ablation.py` — sweeps the 5-D weight
  simplex and reports accuracy / regret / diversity vs. an oracle.
- `docs/routing-weights-ablation.md` — headline findings.

#### Reviewer mapping
- `docs/reviewer-response.md` maps every reviewer concern to the
  exact code, test and doc change that addresses it.

### Changed
- `agentflow.__version__` bumped to `1.1.0`.
- `tests/unit/test_rest_connector.py::_run` now uses
  `asyncio.new_event_loop()` instead of the deprecated
  `asyncio.get_event_loop()` for stable Python 3.10+ test ordering.

### Tests
- 40 new unit tests; full suite: **225 passed**.

## [1.0.0] - 2025

First public release of AgentFlow — a multi-agent framework for AI-powered
enterprise API orchestration.

### Added

#### Core orchestration
- DAG-based execution plans with dependency resolution (`agentflow.core`).
- Multi-agent collaboration system with Planner, Executor, and Validator
  agents (`agentflow.agents`).
- Natural language intent parser for decomposing workflow requests into
  plan steps (`agentflow.nlp`).

#### Connectors
- Connector abstraction layer with a shared `BaseConnector` interface
  (`agentflow.connectors.base`).
- MuleSoft Anypoint Platform connector (`agentflow.connectors.mulesoft`)
  plus an Anypoint Studio demo project under `examples/`.
- REST and GraphQL connectors with pluggable auth
  (`agentflow.connectors.rest`, `agentflow.connectors.graphql`).
- AWS API Gateway connector with SigV4 signing and CloudWatch health
  reporting (`agentflow.connectors.aws`).
- Azure API Management connector with product-policy rate limit handling
  (`agentflow.connectors.azure`).

#### Routing
- Dynamic multi-dimensional router with configurable weight profiles
  (`agentflow.routing.dynamic_router`).
- Budget router with cost-aware endpoint selection and budget exhaustion
  handling (`agentflow.routing.budget_router`).
- Adaptive weight optimizer that tunes routing dimensions against per-SLA
  performance snapshots (`agentflow.routing.adaptive_weight_optimizer`).

#### Resilience
- Adaptive circuit breaker with CLOSED / OPEN / HALF_OPEN states
  (`agentflow.resilience.circuit_breaker`).
- Exponential cooldown strategy with learned decay factors per endpoint
  (`agentflow.resilience.cooldown_strategy`).
- Retry policy with exponential, linear, fibonacci, and adaptive backoff
  plus error classification (`agentflow.resilience.retry_policy`).
- Bulkhead isolation with per-resource concurrency limits and registry
  (`agentflow.resilience.bulkhead`).

#### Observability
- Lightweight OpenTelemetry-style tracer with spans, events, and
  attributes (`agentflow.observability.tracer`).
- Metrics collection surface (`agentflow.observability.metrics`).

#### Caching
- Response cache with pluggable backends
  (`agentflow.caching.response_cache`, `agentflow.caching.backends`).

#### Documentation
- Architecture overview, routing engine guide, circuit breaker guide,
  custom agents guide, and MuleSoft integration guide in `docs/`.
- Contributor guidelines (`CONTRIBUTING.md`) and adoption tracking
  templates under `.github/ISSUE_TEMPLATE/`.

#### Developer experience
- Full test suite across orchestration, routing, resilience, connectors,
  caching, NLP, and observability.
- CI pipeline (GitHub Actions) with ruff lint and pytest.
- `pyproject.toml` with `dev`, `all`, and `mulesoft` extras; mypy strict
  configuration; ruff rules `E, F, I, N, W, UP` at 100-column width.

[Unreleased]: https://github.com/venkatapgummadi/agentflow/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/venkatapgummadi/agentflow/releases/tag/v1.0.0
