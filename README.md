---
<p align="center">
<a href="https://github.com/liatrio-labs/otel-instrumentation-mcp/actions/workflows/build.yml?query=branch%3Amain">
<img alt="Build Status" src="https://img.shields.io/github/actions/workflow/status/liatrio-labs/otel-instrumentation-mcp/build.yml?branch=main&style=for-the-badge">
</a>
<a href="https://codecov.io/gh/liatrio-labs/otel-instrumentation-mcp/branch/main" >
<img alt="Codecov Status" src="https://img.shields.io/codecov/c/github/liatrio-labs/otel-instrumentation-mcp?style=for-the-badge"/>
</a>
<a href="https://github.com/liatrio-labs/otel-instrumentation-mcp/releases">
<img alt="GitHub release" src="https://img.shields.io/github/v/release/liatrio-labs/otel-instrumentation-mcp?include_prereleases&style=for-the-badge">
</a>
<a href="https://api.securityscorecards.dev/projects/github.com/liatrio-labs/otel-instrumentation-mcp/badge">
<img alt="OpenSSF Scorecard" src="https://img.shields.io/ossf-scorecard/github.com/liatrio-labs/otel-instrumentation-mcp?label=openssf%20scorecard&style=for-the-badge">
</a>
</p>
---

# OpenTelemetry MCP Server

A Model Context Protocol (MCP) server that bridges AI coding assistants (like
ClaudeCode, OpenCode, Windsurf, and Cursor) with the OpenTelemetry ecosystem. It
provides real-time access to OpenTelemetry repositories, documentation,
examples, semantic conventions, and the instrumentation score specification to
help engineers implement high-quality observability in their applications.

## Why use this?

OpenTelemetry has extensive documentation and many implementation patterns. This
MCP server helps AI assistants:

- Navigate the complexity of OpenTelemetry documentation
- Provide accurate, up-to-date instrumentation code
- Follow best practices and semantic conventions
- Generate instrumentation that scores qualitatively high
- Avoid common pitfalls and anti-patterns

## Features

The MCP server provides tools and prompts to help AI assistants with
OpenTelemetry tasks:

- **Repository & Issue Access** - Browse OpenTelemetry repositories and search
  issues
- **Examples & Documentation** - Language-specific examples and documentation
- **Semantic Conventions** - Access to standardized attribute definitions
- **Instrumentation Scoring** - Evaluate telemetry quality based on best
  practices
- **AI Prompts** - Analyze code and generate instrumentation suggestions

Additional capabilities:

- **Self-Instrumented** - Full distributed tracing with OpenTelemetry
- **Multi-Transport** - Supports stdio (local), HTTP, and SSE protocols
- **Production Ready** - Kubernetes manifests, health checks, graceful shutdown
- **GitHub Integration** - Authenticated API access via GitHub App or Personal
  Access Token

## Security Notice

Currently supported authentication methods:

- **GitHub Personal Access Token (PAT)** - For individual, local use.
- **GitHub App** - For hosted deployments.

> IMPORTANT: OAuth support is planned for future implementations. Ensure your
> credentials are properly secured and never commit them to version control.

## Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- GitHub authentication (Personal Access Token or GitHub App credentials)

### Installation

1. Clone the repository:

```bash
git clone https://github.com/liatrio-labs/otel-instrumentation-mcp.git
cd otel-instrumentation-mcp
```

2. Install dependencies:

```bash
uv sync
```

3. Set up GitHub authentication (choose one):

**Option A: Personal Access Token**

```bash
export GITHUB_TOKEN="github_pat_..."
```

**Option B: GitHub App (recommended for production)**

```bash
export GITHUB_APP_ID="123456"
export GITHUB_INSTALLATION_ID="654321"
export GITHUB_APP_PRIVATE_KEY_PATH="/path/to/private-key.pem"
```

> NOTE: Additional environment variables can be set, like the
> `OTEL_EXPORTER_OTLP_ENDPOINT`. For a list of available environment
> variables, see [.env.examples](./.env.example)

4. Run the MCP server:

```bash
uv run otel-instrumentation-mcp
```

## Local Development

For development with hot reload and local Kubernetes:

```bash
# Install development dependencies
task install

# Run with Tilt (includes local Kubernetes, OpenTelemetry Collector, hot reload)
tilt up

# Or run development server standalone with hot reload
task dev

# Run tests
task test

# Run linting and formatting
task lint

# Run all checks (test + lint)
task checks
```

## Usage Examples

### Configuration with AI Assistants

#### Claude Desktop

Add to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "otel-instrumentation-mcp": {
      "command": "uv",
      "args": ["run", "otel-instrumentation-mcp"],
      "cwd": "/path/to/otel-instrumentation-mcp",
      "env": {
        "GITHUB_TOKEN": "your_github_token"
      }
    }
  }
}
```

#### Windsurf or Cursor

Add to your MCP configuration file:

```json
{
  "mcpServers": {
    "otel-instrumentation-mcp": {
      "command": "uv",
      "args": ["run", "otel-instrumentation-mcp"],
      "cwd": "/path/to/otel-instrumentation-mcp",
      "env": {
        "GITHUB_TOKEN": "your_github_token"
      }
    }
  }
}
```

### Testing and Development

#### MCP Inspector

```bash
npx @modelcontextprotocol/inspector uv run otel-instrumentation-mcp
```

#### Using HTTP/SSE Transports (Remote Access)

For network-accessible deployments:

```bash
# HTTP Transport
SERVICE_PORT=8080 uv run otel-instrumentation-mcp
# Access at: http://localhost:8080/mcp/

# SSE Transport
MCP_TRANSPORT=sse MCP_PORT=8080 uv run otel-instrumentation-mcp
# Access at: http://localhost:8080/
```

> **Note**: Remote access currently requires GitHub authentication configured via
> environment variables. OAuth support for client authentication is coming soon.

## Real-World Example: Instrumenting Your Code

Once configured, you can ask your AI assistant to help with OpenTelemetry
instrumentation:

```
User: Help me add OpenTelemetry instrumentation to my Python Flask application

AI Assistant: I'll help you add OpenTelemetry instrumentation to your Flask
application. Let me first check the latest OpenTelemetry documentation and
examples for Python.

[Uses get_opentelemetry_docs_by_language tool]
[Uses get_opentelemetry_examples_by_language tool]
[Uses get_semantic_conventions tool]

Based on the latest OpenTelemetry documentation, here's how to properly
instrument your Flask application...

[Provides relatively accurate* up-to-date instrumentation code following best
practices]
```

## Production Deployment

### Kubernetes

The repository includes Kubernetes manifests with:

- Deployment with health checks and resource limits
- Service for internal communication
- OpenTelemetry Collector integration
- ConfigMaps for feature flags
- Support for different environments via the Kustomize overlay pattern (dev,
  local, prod)

```bash
# Example
kubectl apply -k manifests/overlays/prod
```

## Configuration

### Environment Variables

| Variable                      | Description                                  | Default                           |
| ----------------------------- | -------------------------------------------- | --------------------------------- |
| `SERVICE_NAME`                | Service name for telemetry                   | `otel-instrumentation-mcp-server` |
| `SERVICE_VERSION`             | Service version                              | `0.15.0`                          |
| `SERVICE_INSTANCE_ID`         | Instance identifier                          | `local`                           |
| `SERVICE_PORT`                | Port for HTTP transport (overrides MCP_PORT) | -                                 |
| `MCP_TRANSPORT`               | Transport type (`stdio`, `http`, `sse`)      | `stdio`                           |
| `MCP_HOST`                    | Host binding for HTTP/SSE                    | Auto-detected                     |
| `MCP_PORT`                    | Port for HTTP/SSE transport                  | `8080`                            |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint                      | `http://localhost:4317`           |

### GitHub Authentication

Choose one authentication method:

**GitHub App (Recommended):**

- `GITHUB_APP_ID` - GitHub App ID
- `GITHUB_INSTALLATION_ID` - Installation ID
- `GITHUB_APP_PRIVATE_KEY_PATH` - Path to private key

**Personal Access Token:**

- `GITHUB_TOKEN` - GitHub personal access token

## Development

### Running Tests

```bash
# Run all tests
task test

# Run specific test
task test-single -- tests/test_main.py::test_list_opentelemetry_repos_tool

# Run with coverage
task test-coverage
```

### Linting and Formatting

```bash
# Run all checks
task checks

# Format code
task lint
```

### Development Server

```bash
# Start with hot reload
task dev

# Custom port
SERVICE_PORT=3000 task dev
```

## Observability

The MCP server is fully instrumented with OpenTelemetry, providing:

- Distributed tracing for MCP operations
- Custom semantic conventions for MCP and GenAI specific attributes
- Integration with standard OpenTelemetry collectors
- High instrumentation quality (measured with [Instrumentation Score](https://github.com/instrumentation-score/spec))

View traces in your preferred backend (Jaeger, Honeycomb, Datadog, Dash0, etc.)
by configuring `OTEL_EXPORTER_OTLP_ENDPOINT`.

## Architecture

- **FastMCP Framework** - Provides MCP protocol implementation
- **OpenTelemetry SDK** - Full observability with auto-instrumentation
- **Async Python** - High-performance async/await patterns
- **GitHub GraphQL API** - Efficient data fetching from repositories
- **Multi-transport** - Flexible deployment options (stdio, HTTP, SSE)

## Roadmap

### Coming Soon

- **OAuth Support** - Full OAuth flow for MCP authentication
- **Caching Layer** - Native caching for GitHub API responses to improve
  performance
- **Weaver Custom Semantic Conventions** - Support for custom semantic
  convention registries through Weaver.

### Known Limitations

- OAuth flow for MCPs isn't implemented yet.
- GitHub API rate limits apply organizationally when self-hosting through an
  app.
- Currently optimized for OpenTelemetry repositories only.

## Contributing

We welcome contributions! Please submit issues and pull requests on GitHub. See
[CONTRIBUTING.md](./CONTRIBUTING.md) to get started.

## License

This project is licensed under the Apache License 2.0 - see the
[LICENSE](LICENSE) file for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/liatrio/otel-instrumentation-mcp/issues)
- **Discussions**: [GitHub Discussions](https://github.com/liatrio/otel-instrumentation-mcp/discussions)

## Notice of Attribution

This is a derived worked from @sgsharma's original
[otel-instrumentation-mcp][otel-instrumentation-mcp] at [this commit][cmt].

[otel-instrumentation-mcp]: https://github.com/sgsharma/otel-instrumentation-mcp
[cmt]: https://github.com/sgsharma/otel-instrumentation-mcp/commit/0cea25dd127a403bf3a8e29e1645cc606bf64b66
