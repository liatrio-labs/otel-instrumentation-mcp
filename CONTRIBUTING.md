# Contributing to OpenTelemetry MCP Server

We welcome contributions! This guide will help you get started.

## Quick Start

1. **Fork and clone** the repository
2. **Install dependencies**: `task install` or `uv sync`
3. **Set up GitHub authentication** (see [README.md](./README.md#installation))
4. **Run tests**: `task test`
5. **Make your changes** following our [code style guidelines](#code-style)
6. **Submit a pull request**

## Development Commands

```bash
# Install dependencies
task install

# Run all tests
task test

# Run specific test
task test-single -- tests/test_main.py::test_list_opentelemetry_repos_tool

# Format and lint code
task lint

# Run all checks (test + lint)
task checks

# Start development server
task dev
```

## Code Style

- **Python 3.13+** required
- **Imports**: Group stdlib, third-party, local imports
- **Type hints**: Required for all function parameters and return values
- **Async/await**: Prefer async patterns for MCP tools
- **Naming**: Use `snake_case` for functions/variables, `PascalCase` for classes
- **Testing**: Use pytest with async MCP client patterns
- **Formatting**: Pre-commit hooks handle formatting automatically

## Pull Request Guidelines

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation changes
- `test:` for test additions/changes
- `feat(refactor):` for code refactoring

### PR Requirements

- Keep PRs focused and under 200 lines when possible
- Include tests for new functionality
- Update documentation if needed
- Ensure all checks pass (`task checks`)
- Link to related issues

### Review Process

- PRs require approval from maintainers
- Address feedback promptly
- Squash commits before merging

## Reporting Issues

When reporting bugs, include:

- Expected vs actual behavior
- Steps to reproduce
- Environment details (Python version, OS, etc.)
- Relevant logs or error messages

## Questions?

- **Issues**: [GitHub Issues](https://github.com/liatrio/otel-instrumentation-mcp/issues)
- **Discussions**: [GitHub Discussions](https://github.com/liatrio/otel-instrumentation-mcp/discussions)

Thank you for contributing to the OpenTelemetry MCP Server! 🚀
