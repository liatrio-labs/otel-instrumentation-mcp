FROM python:3.13-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create non-root user
ARG UID=10001
RUN adduser --disabled-password --gecos "" --uid ${UID} appuser

# Set working directory
WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock README.md ./

# Copy application code
COPY otel_instrumentation_mcp/ ./otel_instrumentation_mcp/

# Install dependencies using uv with proper resolution from pyproject.toml
RUN uv sync --no-dev --frozen

# Change ownership to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Expose port (for SSE transport if needed)
EXPOSE 8080

# Run the MCP server using the entry point script
CMD [".venv/bin/otel-mcp"]
