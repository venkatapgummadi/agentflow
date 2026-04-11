# Contributing to AgentFlow

Thank you for your interest in contributing to AgentFlow! This project welcomes contributions from the community.

## How to Contribute

### Reporting Issues
- Use GitHub Issues to report bugs or suggest features
- Include Python version, OS, and steps to reproduce

### Pull Requests
1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Write tests for your changes
4. Ensure all tests pass
5. Submit a pull request with a clear description

### Development Setup
```bash
git clone https://github.com/venkatapgummadi/agentflow.git
cd agentflow
pip install -e ".[dev]"
pytest tests/ -v
```

### Areas for Contribution
- **New Connectors**: GraphQL, gRPC, AWS API Gateway, Azure APIM
- **Routing Strategies**: Custom scoring functions, ML-based routing
- **NLP Improvements**: Better intent parsing, LLM integration
- **Resilience Patterns**: Bulkhead, timeout policies
- **Documentation**: Tutorials, API reference, architecture guides
- **Testing**: Integration tests, performance benchmarks

## Code Style
- Python 3.10+ with type hints
- Format with `ruff`
- Docstrings on all public methods

## License
By contributing, you agree that your contributions will be licensed under Apache 2.0.
