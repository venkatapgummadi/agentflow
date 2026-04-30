# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

## [Unreleased]

### Added
- Unit tests for `RetryPolicy` covering all four backoff strategies
  (exponential, linear, fibonacci, adaptive), error classification, retry
  decisions, jitter bounds, and the backoff cap.

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
