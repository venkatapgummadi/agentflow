# AgentFlow

### A Multi-Agent Framework for AI-Powered Enterprise API Orchestration

[![CI](https://github.com/venkatapgummadi/agentflow/actions/workflows/ci.yml/badge.svg)](https://github.com/venkatapgummadi/agentflow/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![PyPI version](https://img.shields.io/pypi/v/agentflow.svg)](https://pypi.org/project/agentflow/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**AgentFlow** is a production-grade Python framework where autonomous AI agents dynamically orchestrate, compose, and self-heal API workflows across enterprise integration platforms — with first-class MuleSoft Anypoint support.

## The Problem

Modern enterprises run hundreds of APIs across MuleSoft, AWS API Gateway, Azure APIM, and custom services. Composing these APIs into reliable workflows requires:

- **Static orchestration** that breaks when APIs change
- **Manual error handling** per integration point
- **No intelligent routing** based on latency, cost, or capability
- **Zero natural-language accessibility** for non-technical stakeholders

## The Solution

AgentFlow introduces **autonomous AI agents** that understand API capabilities semantically and can:

1. **Parse natural-language intents** into executable API workflows
2. **Dynamically discover and compose** APIs at runtime
3. **Route intelligently** based on latency, cost, rate limits, and capability matching
4. **Self-heal** with circuit breakers, adaptive retries, and fallback chains
5. **Collaborate** via a multi-agent protocol for complex cross-platform orchestrations

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  Intent Layer                     │
│   Natural Language → Structured API Plan          │
├─────────────────────────────────────────────────┤
│              Agent Orchestrator                   │
│   ┌──────────┐ ┌──────────┐ ┌──────────────┐    │
│   │ Planner  │ │ Executor │ │  Validator    │    │
│   │  Agent   │ │  Agent   │ │    Agent      │    │
│   └──────────┘ └──────────┘ └──────────────┘    │
├─────────────────────────────────────────────────┤
│            Dynamic Router                        │
│   Latency │ Cost │ Rate Limit │ Capability       │
├─────────────────────────────────────────────────┤
│           Resilience Layer                       │
│   Circuit Breaker │ Retry │ Fallback │ Bulkhead  │
├─────────────────────────────────────────────────┤
│              Connector Layer                     │
│   MuleSoft │ REST │ GraphQL │ gRPC │ Custom      │
└─────────────────────────────────────────────────┘
```

## Quick Start

```python
from agentflow import AgentOrchestrator, MuleSoftConnector

# Initialize with MuleSoft Anypoint
orchestrator = AgentOrchestrator(
    connectors=[
        MuleSoftConnector(
            anypoint_url="https://anypoint.mulesoft.com",
            org_id="your-org-id",
            environment="production"
        )
    ]
)

# Natural language orchestration
result = await orchestrator.execute(
    "Fetch customer 12345 from CRM, enrich with credit score, "
    "and create a loan application if score > 700"
)

# Or use the typed API
from agentflow.agents import PlannerAgent, ExecutorAgent

plan = await PlannerAgent().create_plan(
    intent="Sync inventory across all warehouses",
    available_apis=orchestrator.discover_apis()
)
result = await ExecutorAgent().execute_plan(plan)
```

## Key Features

### Multi-Agent Collaboration
Each orchestration is handled by specialized agents (Planner, Executor, Validator) that communicate through a shared context and can negotiate execution strategies.

### MuleSoft-Native
First-class integration with MuleSoft Anypoint Platform: auto-discovery of APIs from Exchange, RAML/OAS parsing, CloudHub deployment awareness, and runtime policy compliance.

### Intelligent Routing
The Dynamic Router scores candidate APIs on latency (P95), cost-per-call, current rate-limit headroom, and semantic capability match — then selects the optimal endpoint in real time.

### Self-Healing Resilience
Adaptive circuit breakers learn from failure patterns. Retry policies adjust backoff based on error classification. Fallback chains provide graceful degradation.

## Installation

```bash
pip install agentflow
```

## Documentation

See the [docs/](docs/) directory for detailed guides:

- [Architecture Deep Dive](docs/architecture.md)
- [MuleSoft Integration Guide](docs/mulesoft_guide.md)
- [Writing Custom Agents](docs/custom_agents.md)
- [Routing Strategies](docs/routing.md)

## Who's Using AgentFlow?

Are you using AgentFlow at your company or in a project? We'd love to hear from you!

👉 **[Open an Adoption Story issue](../../issues/new?template=adoption-story.md)** — takes 2 minutes and helps the project grow.

| Company / Project | Industry | Use Case |
|---|---|---|
| *Your company here* | *Your industry* | *[Share your story →](../../issues/new?template=adoption-story.md)* |

## Community

| Channel | Purpose |
|---|---|
| [💬 Discussions — Show & Tell](../../discussions/categories/show-and-tell) | Share what you built |
| [❓ Discussions — Q&A](../../discussions/categories/q-a) | Ask questions |
| [🔌 Integration Requests](../../issues/new?template=integration-request.md) | Request a new connector |
| [✨ Feature Requests](../../issues/new?template=feature-request.md) | Suggest improvements |
| [🐛 Bug Reports](../../issues/new?template=bug-report.md) | Report issues |

If AgentFlow saves you time or solves a real problem, a ⭐ on this repo goes a long way — it helps more engineers find the framework.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=venkatapgummadi/agentflow&type=Date)](https://star-history.com/#venkatapgummadi/agentflow&Date)

## Contributing

Pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the dev workflow, and check the [`good first issue`](../../issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) and [`help wanted`](../../issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) labels for places to start. By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.

## Author

**Venkata Pavan Kumar Gummadi**
- Research focus: AI-driven API orchestration and enterprise integration intelligence
- [GitHub](https://github.com/venkatapgummadi)
- [LinkedIn](https://www.linkedin.com/in/venkata-p-1841146/)
- [IEEE](https://ieee.org) Member
