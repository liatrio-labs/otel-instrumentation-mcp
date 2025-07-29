"""Tests for rate limiting error handling with proper span attributes."""

import pytest
from unittest.mock import Mock, patch
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from otel_instrumentation_mcp.telemetry import handle_rate_limit_error


@pytest.fixture
def tracer_with_exporter():
    """Create a tracer with in-memory span exporter for testing."""
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = tracer_provider.get_tracer(__name__)
    return tracer, exporter


def test_handle_rate_limit_error_with_github_headers(tracer_with_exporter):
    """Test rate limit handling with GitHub-style headers."""
    tracer, exporter = tracer_with_exporter

    # Create a mock response with GitHub rate limit headers
    mock_response = Mock()
    mock_response.status_code = 403
    mock_response.headers = {
        "x-ratelimit-remaining": "0",
        "x-ratelimit-limit": "5000",
        "x-ratelimit-reset": "1640995200",  # Unix timestamp
        "x-ratelimit-used": "5000",
        "x-ratelimit-resource": "core",
        "retry-after": "3600",
    }

    with tracer.start_as_current_span("test_operation") as span:
        error_info = handle_rate_limit_error(
            span,
            mock_response,
            "test_github_api_call",
            repository="open-telemetry/opentelemetry-python",
            query="test query",
        )

    # Verify error info structure
    assert error_info["error_type"] == "rate_limit"
    assert error_info["status_code"] == 403
    assert error_info["retry_recommended"] is True
    assert "rate_limit_info" in error_info
    assert "request_context" in error_info

    # Verify span attributes
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Check error attributes (now uses HTTP status code as error type per semantic conventions)
    assert span.attributes.get("error.type") == "403"
    assert span.attributes.get("error.rate_limit.operation") == "test_github_api_call"
    assert span.attributes.get("error.rate_limit.status_code") == "403"
    assert span.attributes.get("error.rate_limit.rate_limit_remaining") == "0"
    assert span.attributes.get("error.rate_limit.rate_limit_limit") == "5000"
    assert span.attributes.get("error.rate_limit.rate_limit_resource") == "core"

    # Check request context
    assert (
        span.attributes.get("error.rate_limit.request.repository")
        == "open-telemetry/opentelemetry-python"
    )
    assert span.attributes.get("error.rate_limit.request.query") == "test query"

    # Check span events
    events = span.events
    assert len(events) == 1
    event = events[0]
    assert event.name == "rate_limit_encountered"
    assert event.attributes["operation"] == "test_github_api_call"
    assert event.attributes["status_code"] == 403


def test_handle_rate_limit_error_with_429_status(tracer_with_exporter):
    """Test rate limit handling with 429 status code."""
    tracer, exporter = tracer_with_exporter

    # Create a mock response with 429 status
    mock_response = Mock()
    mock_response.status_code = 429
    mock_response.headers = {"retry-after": "60"}

    with tracer.start_as_current_span("test_operation") as span:
        error_info = handle_rate_limit_error(span, mock_response, "test_api_call")

    # Verify error info
    assert error_info["error_type"] == "rate_limit"
    assert error_info["status_code"] == 429
    assert error_info["retry_after_seconds"] == 60

    # Verify span attributes
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.attributes.get("http.response.status_code") == 429
    assert span.attributes.get("error.type") == "429"
    assert span.attributes.get("error.rate_limit.retry_after") == "60"


def test_handle_rate_limit_error_minimal_headers(tracer_with_exporter):
    """Test rate limit handling with minimal headers."""
    tracer, exporter = tracer_with_exporter

    # Create a mock response with minimal headers
    mock_response = Mock()
    mock_response.status_code = 403
    mock_response.headers = {}

    with tracer.start_as_current_span("test_operation") as span:
        error_info = handle_rate_limit_error(span, mock_response, "minimal_test")

    # Should still work with minimal info
    assert error_info["error_type"] == "rate_limit"
    assert error_info["status_code"] == 403
    assert error_info["retry_recommended"] is True

    # Verify span still gets basic attributes
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.attributes.get("error.type") == "403"
    assert span.attributes.get("error.rate_limit.operation") == "minimal_test"


@pytest.mark.asyncio
async def test_github_issues_rate_limit_integration():
    """Test that GitHub issues module handles rate limiting gracefully."""
    from otel_instrumentation_mcp.github_issues import get_repo_issues

    # Mock requests.post to return a 403 rate limit response
    mock_response = Mock()
    mock_response.status_code = 403
    mock_response.content = b'{"message": "API rate limit exceeded"}'
    mock_response.headers = {
        "x-ratelimit-remaining": "0",
        "x-ratelimit-limit": "5000",
        "x-ratelimit-reset": "1640995200",
    }

    with patch(
        "otel_instrumentation_mcp.github_issues.requests.post",
        return_value=mock_response,
    ):
        # Should return empty list instead of raising exception
        result = await get_repo_issues("opentelemetry-python")
        assert result == []


@pytest.mark.asyncio
async def test_opentelemetry_repos_rate_limit_integration():
    """Test that OpenTelemetry repos module handles rate limiting gracefully."""
    from otel_instrumentation_mcp.opentelemetry_repos import get_opentelemetry_repos
    import os

    # Mock requests.post to return a 429 rate limit response
    mock_response = Mock()
    mock_response.status_code = 429
    mock_response.content = b'{"message": "API rate limit exceeded"}'
    mock_response.headers = {"retry-after": "3600"}

    # Set a GitHub token to ensure the function tries to make a real request
    # Need to patch the GITHUB_TOKEN constant in the module
    with patch.dict(os.environ, {"GITHUB_TOKEN": "fake_token"}):
        with patch(
            "otel_instrumentation_mcp.opentelemetry_repos.GITHUB_TOKEN", "fake_token"
        ):
            with patch(
                "otel_instrumentation_mcp.opentelemetry_repos.requests.post",
                return_value=mock_response,
            ):
                # Should return empty list instead of raising exception
                result = get_opentelemetry_repos()
                assert result == []


def test_rate_limit_reset_time_calculation(tracer_with_exporter):
    """Test calculation of rate limit reset time."""
    import time

    tracer, exporter = tracer_with_exporter

    # Create a mock response with future reset time
    future_time = int(time.time()) + 3600  # 1 hour from now
    mock_response = Mock()
    mock_response.status_code = 403
    mock_response.headers = {"x-ratelimit-reset": str(future_time)}

    with tracer.start_as_current_span("test_operation") as span:
        error_info = handle_rate_limit_error(
            span, mock_response, "test_reset_calculation"
        )

    # Should calculate reset time correctly (approximately 3600 seconds)
    reset_seconds = error_info["rate_limit_info"]["rate_limit_reset_in_seconds"]
    assert 3590 <= reset_seconds <= 3610  # Allow some variance for test execution time

    # Verify span attribute
    spans = exporter.get_finished_spans()
    span = spans[0]
    assert span.attributes.get("error.rate_limit.rate_limit_reset_in_seconds") == str(
        reset_seconds
    )
