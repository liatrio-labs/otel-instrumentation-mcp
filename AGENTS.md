# Agent Guidelines for otel-instrumentation-mcp

## Build/Test Commands
- **Install dependencies**: `task install` or `uv sync`
- **Run all tests**: `task test` or `uv run pytest`
- **Run single test**: `task test-single -- tests/test_main.py::test_specific_function`
- **Format code**: `task lint` or `uv run black otel_instrumentation_mcp/ tests/`
- **Development server**: `task dev` (starts with hot reload on port 8080)
- **Build Docker**: `task build` (runs tests + lint first)

## Code Style Guidelines
- **License headers**: All Python files must include Apache 2.0 license header (use `task addlicense`)
- **Formatting**: Use Black formatter (configured in pyproject.toml dev dependencies)
- **Imports**: Standard library first, then third-party, then local imports with blank lines between groups
- **Type hints**: Use type hints for function parameters and return values
- **Async functions**: Use async/await pattern for I/O operations
- **Error handling**: Use try/except blocks with proper logging via `logger.error(..., exc_info=True)`
- **Telemetry**: Instrument functions with OpenTelemetry spans using `tracer.start_as_current_span()`
- **Logging**: Use structured logging with `extra` dict for additional context
- **Naming**: Use snake_case for functions/variables, PascalCase for classes
- **Docstrings**: Use Google-style docstrings with Args/Returns sections

## Testing
- Use pytest with async support (`pytest-asyncio`)
- Test files in `tests/` directory with `test_` prefix
- Use MCP client session for integration tests
- Mock external API calls when appropriate