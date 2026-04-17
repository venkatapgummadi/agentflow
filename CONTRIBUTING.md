# Contributing to AgentFlow

Thanks for your interest in contributing! AgentFlow is an open-source framework for AI-driven enterprise API orchestration, and contributions of all sizes — typo fixes, new connectors, benchmarks, docs — are welcome.

## Table of contents

- [Ways to contribute](#ways-to-contribute)
- [Good first issues](#good-first-issues)
- [Development setup](#development-setup)
- [Branching and commit conventions](#branching-and-commit-conventions)
- [Pull request checklist](#pull-request-checklist)
- [Code style](#code-style)
- [Testing](#testing)
- [Reporting bugs and requesting features](#reporting-bugs-and-requesting-features)
- [Code of Conduct](#code-of-conduct)

## Ways to contribute

| Area | Examples |
|---|---|
| **New connectors** | GraphQL, gRPC, AWS API Gateway, Azure APIM, Kong, Apigee |
| **Routing strategies** | Custom scoring functions, ML-based routing, cost-aware routing |
| **NLP / intent parsing** | LLM integration (OpenAI, Anthropic, local models), better few-shot prompts |
| **Resilience patterns** | Bulkhead, timeout policies, hedged requests, fallback chains |
| **Documentation** | Tutorials, end-to-end examples, architecture deep-dives, video walkthroughs |
| **Testing** | Integration tests against mock APIs, performance benchmarks, fuzz tests |
| **Examples** | Industry workflows (fintech, healthcare, retail), real MuleSoft scenarios |

## Good first issues

If you're new to the project, look for issues labeled [`good first issue`](https://github.com/venkatapgummadi/agentflow/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) or [`help wanted`](https://github.com/venkatapgummadi/agentflow/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22). Good starter ideas include:

- Add a connector skeleton for a new platform (REST, GraphQL, gRPC)
- Improve docstrings and add type hints to legacy modules
- Add unit tests for one of the resilience policies
- Write a new example under `examples/` for an industry vertical
- Improve error messages in the orchestrator

Don't see what you want to work on? Open an issue describing the change first so we can align on the approach.

## Development setup

```bash
git clone https://github.com/venkatapgummadi/agentflow.git
cd agentflow

# Create an isolated environment (recommended)
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate

# Install in editable mode with dev + optional extras
pip install -e ".[dev,all,mulesoft]"

# Run the test suite
pytest tests/ -v

# Run linting
ruff check agentflow/ tests/

# Run type checks
mypy agentflow/
```

Python 3.10 or newer is required.

## Branching and commit conventions

- Branch off `main`. Use a descriptive prefix:
  - `feature/<short-name>` — new functionality
  - `fix/<short-name>` — bug fixes
  - `docs/<short-name>` — documentation only
  - `chore/<short-name>` — tooling, refactors with no behavior change
- Keep commits focused. Squash noise locally before opening a PR.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) where practical:
  - `feat(router): add cost-aware scoring`
  - `fix(circuit-breaker): reset half-open state on success`
  - `docs(readme): clarify quickstart`

## Pull request checklist

Before requesting review, please confirm:

- [ ] The change has a clear motivation in the PR description (and a linked issue if non-trivial)
- [ ] New code has type hints and docstrings on public methods
- [ ] Tests are added or updated, and `pytest` passes locally
- [ ] `ruff check` passes with no warnings
- [ ] Public-API changes are reflected in `README.md` and the relevant doc under `docs/`
- [ ] CHANGELOG entry added if applicable
- [ ] No secrets, tokens, or proprietary URLs in code or fixtures

PRs that touch core orchestration or resilience logic should include a benchmark or behavior comparison where possible.

## Code style

- Python 3.10+ with type hints everywhere
- Format and lint with [`ruff`](https://github.com/astral-sh/ruff) (config in `pyproject.toml`)
- Line length 100
- Async-first: prefer `async def` for I/O-bound code
- Docstrings on all public classes and methods (Google or NumPy style)

## Testing

```bash
# Full suite
pytest tests/ -v

# Just unit tests
pytest tests/unit -v

# With coverage
pytest tests/ --cov=agentflow --cov-report=term-missing
```

When adding a new connector or agent, please add at least:

1. A unit test covering the happy path and one failure mode
2. An example under `examples/` if it's a user-facing capability

## Reporting bugs and requesting features

Use the issue templates:

- [🐛 Bug report](.github/ISSUE_TEMPLATE/bug-report.md) — include Python version, OS, and a minimal reproduction
- [✨ Feature request](.github/ISSUE_TEMPLATE/feature-request.md)
- [🔌 Integration request](.github/ISSUE_TEMPLATE/integration-request.md) — for new connectors
- [⭐ Adoption story](.github/ISSUE_TEMPLATE/adoption-story.md) — tell us how you're using AgentFlow

For security issues, please follow the disclosure process in [SECURITY.md](SECURITY.md) instead of filing a public issue.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it. Please report unacceptable behavior to the maintainer at venkata.p.gummadi@ieee.org.

## License

By contributing, you agree that your contributions will be licensed under the project's [Apache 2.0 License](LICENSE).
