# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
