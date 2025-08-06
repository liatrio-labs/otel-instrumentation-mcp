# Copyright 2025 Liatrio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""OpenTelemetry telemetry configuration and utilities."""

import logging
import os
from typing import Optional

from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.trace import Status, StatusCode


class TelemetryConfig:
    """Centralized OpenTelemetry configuration and setup."""

    def __init__(self):
        self.service_name = os.getenv("SERVICE_NAME", "otel-instrumentation-mcp-server")
        self.service_instance_id = os.getenv("SERVICE_INSTANCE_ID", "local")
        self.otlp_endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
        )

        self._tracer: Optional[trace.Tracer] = None
        self._meter: Optional[metrics.Meter] = None
        self._logger: Optional[logging.Logger] = None
        self._initialized = False

    def initialize(self) -> None:
        """Initialize OpenTelemetry SDK with proper configuration."""
        if self._initialized:
            return

        # Create resource with service information following semantic conventions
        resource = Resource.create(
            {
                # Standard service attributes
                ResourceAttributes.SERVICE_NAME: self.service_name,
                ResourceAttributes.SERVICE_INSTANCE_ID: self.service_instance_id,
                ResourceAttributes.DEPLOYMENT_ENVIRONMENT: os.getenv(
                    "DEPLOYMENT_ENVIRONMENT", "development"
                ),
                # Additional semantic convention attributes
                "service.namespace": "opentelemetry",
                "service.type": "mcp_server",
                "telemetry.sdk.name": "opentelemetry",
                "telemetry.sdk.language": "python",
                # Process attributes
                "process.pid": os.getpid(),
                "process.executable.name": "python",
                # Host attributes (if available)
                "host.name": os.getenv("HOSTNAME", "localhost"),
            }
        )

        # Configure tracing
        self._setup_tracing(resource)

        # Configure metrics
        self._setup_metrics(resource)

        # Configure logging bridge
        self._setup_logging()

        # Auto-instrument libraries
        self._setup_auto_instrumentation()

        self._initialized = True

    def _setup_tracing(self, resource: Resource) -> None:
        """Configure OpenTelemetry tracing."""
        # Create tracer provider
        tracer_provider = TracerProvider(resource=resource)

        # Create OTLP span exporter
        span_exporter = OTLPSpanExporter(endpoint=self.otlp_endpoint)

        # Add batch span processor
        span_processor = BatchSpanProcessor(span_exporter)
        tracer_provider.add_span_processor(span_processor)

        # Set global tracer provider
        trace.set_tracer_provider(tracer_provider)

        # Create tracer
        self._tracer = trace.get_tracer(__name__)

    def _setup_metrics(self, resource: Resource) -> None:
        """Configure OpenTelemetry metrics."""
        # Create metric exporter
        metric_exporter = OTLPMetricExporter(endpoint=self.otlp_endpoint)

        # Create metric reader
        metric_reader = PeriodicExportingMetricReader(
            exporter=metric_exporter,
            export_interval_millis=30000,  # Export every 30 seconds
        )

        # Create meter provider
        meter_provider = MeterProvider(
            resource=resource, metric_readers=[metric_reader]
        )

        # Set global meter provider
        metrics.set_meter_provider(meter_provider)

        # Create meter
        self._meter = metrics.get_meter(__name__)

    def _setup_logging(self) -> None:
        """Configure OpenTelemetry logging bridge."""
        # Instrument logging to correlate with traces
        LoggingInstrumentor().instrument(set_logging_format=True)

        # Create logger with trace correlation
        self._logger = logging.getLogger(self.service_name)
        self._logger.setLevel(logging.INFO)

        # Configure formatter to include trace information
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - "
            "[trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] - %(message)s"
        )

        # Update existing handlers
        for handler in self._logger.handlers:
            handler.setFormatter(formatter)

    def _setup_auto_instrumentation(self) -> None:
        """Configure selective instrumentation for libraries.

        We completely disable auto-instrumentation to avoid noisy traces from:
        - Internal SSE POST/PUT messages
        - FastAPI internal routing
        - HTTP client requests

        Instead, we use manual instrumentation only for MCP operations.
        """
        # All instrumentation is handled manually in MCP tool/prompt decorators
        pass

    @property
    def tracer(self) -> trace.Tracer:
        """Get the configured tracer."""
        if not self._initialized:
            self.initialize()
        return self._tracer

    @property
    def meter(self) -> metrics.Meter:
        """Get the configured meter."""
        if not self._initialized:
            self.initialize()
        return self._meter

    @property
    def logger(self) -> logging.Logger:
        """Get the configured logger with trace correlation."""
        if not self._initialized:
            self.initialize()
        if self._logger is None:
            raise RuntimeError("Logger not properly initialized")
        return self._logger


# Global telemetry instance
telemetry = TelemetryConfig()


def get_tracer() -> trace.Tracer:
    """Get the global tracer instance."""
    return telemetry.tracer


def get_meter() -> metrics.Meter:
    """Get the global meter instance."""
    return telemetry.meter


def get_logger() -> logging.Logger:
    """Get the global logger instance with trace correlation."""
    return telemetry.logger


def set_span_error(span: trace.Span, error: Exception) -> None:
    """Set span status to error and record exception details."""
    span.set_status(Status(StatusCode.ERROR, str(error)))
    span.record_exception(error)


def add_span_attributes(span: trace.Span, **attributes) -> None:
    """Add multiple attributes to a span safely."""
    for key, value in attributes.items():
        if value is not None:
            # Convert to string if not already
            if not isinstance(value, (str, int, float, bool)):
                value = str(value)
            span.set_attribute(key, value)


def create_root_span_context(
    tracer: trace.Tracer,
    operation_name: str,
    operation_type: str = "mcp",
    session_id: Optional[str] = None,
):
    """Create a true root span context manager for MCP operations.

    This creates a completely new trace with no parent context, ensuring
    each MCP operation gets its own root span and eliminating noise from
    HTTP transport layers.

    Args:
        tracer: The OpenTelemetry tracer instance
        operation_name: Name of the operation (e.g., 'mcp.tool.list_repos')
        operation_type: Type of operation ('mcp', 'tool', 'prompt')
        session_id: Optional session identifier for SSE connections

    Returns:
        Context manager that yields a root span with proper context
    """
    from opentelemetry import context as otel_context
    from opentelemetry.trace import set_span_in_context

    # Build comprehensive attributes for the root span
    attributes = {
        "operation.type": operation_type,
        "mcp.operation": operation_name,
    }

    # Add tool or prompt specific attributes
    if operation_type == "tool":
        attributes[MCPAttributes.MCP_TOOL_NAME] = operation_name.split(".")[-1]
    elif operation_type == "prompt":
        attributes[MCPAttributes.MCP_PROMPT_NAME] = operation_name.split(".")[-1]

    # Add session tracking for SSE connections
    if session_id:
        attributes[MCPAttributes.MCP_SESSION_ID] = session_id
        attributes[MCPAttributes.MCP_TRANSPORT] = "sse"
        attributes[MCPAttributes.MCP_SESSION_TYPE] = "sse"
        # Add network attributes for SSE transport
        attributes.update(
            {
                SpanAttributes.NETWORK_PROTOCOL_NAME: "http",
                SpanAttributes.NETWORK_TRANSPORT: "tcp",
                SpanAttributes.NETWORK_TYPE: "ipv4",  # Default, could be detected
            }
        )
    else:
        # Detect transport from environment if no session
        transport = os.getenv("MCP_TRANSPORT", "stdio")
        attributes[MCPAttributes.MCP_TRANSPORT] = transport

        # Add network attributes based on transport
        if transport == "http":
            attributes.update(
                {
                    SpanAttributes.NETWORK_PROTOCOL_NAME: "http",
                    SpanAttributes.NETWORK_TRANSPORT: "tcp",
                    SpanAttributes.NETWORK_TYPE: "ipv4",
                }
            )
        elif transport == "stdio":
            # For stdio, it's inter-process communication
            attributes.update(
                {
                    SpanAttributes.NETWORK_TRANSPORT: "pipe",
                }
            )

    # Create a completely new, empty context (no parent trace)
    empty_context = otel_context.Context()

    # Start a new root span with the empty context
    span = tracer.start_span(
        name=operation_name,
        context=empty_context,
        attributes=attributes,
    )

    # Create a new context with this span as the current span
    span_context = set_span_in_context(span, empty_context)

    # Return a context manager that properly manages the span lifecycle
    class RootSpanContextManager:
        def __enter__(self):
            # Activate the span context
            self.token = otel_context.attach(span_context)
            return span

        def __exit__(self, exc_type, exc_val, exc_tb):
            # Handle exceptions
            if exc_type is not None:
                span.set_status(Status(StatusCode.ERROR, str(exc_val)))
                span.record_exception(exc_val)
            else:
                span.set_status(Status(StatusCode.OK))

            # End the span and detach context
            span.end()
            otel_context.detach(self.token)

    return RootSpanContextManager()


def add_enhanced_error_attributes(
    span: trace.Span, error: Exception, **context
) -> None:
    """Add enhanced error attributes to a span using semantic conventions.

    Args:
        span: The span to add error attributes to
        error: The exception that occurred
        **context: Additional context attributes to add
    """
    # Determine error type following semantic conventions
    error_type = _get_semantic_error_type(error)

    # Use official semantic convention for error type
    span.set_attribute(ERROR_TYPE, error_type)
    span.set_attribute(SpanAttributes.EXCEPTION_MESSAGE, str(error))

    # Add any additional context
    for key, value in context.items():
        if value is not None:
            span.set_attribute(f"error.context.{key}", str(value))

    # Set the span status and record exception
    set_span_error(span, error)


def _get_semantic_error_type(error: Exception) -> str:
    """Get semantic convention compliant error type from exception.

    Args:
        error: The exception to classify

    Returns:
        Error type string following semantic conventions
    """
    error_class = error.__class__.__name__

    # Map common exceptions to semantic convention error types
    error_type_mapping = {
        "TimeoutError": "timeout",
        "ConnectionError": "connection_error",
        "ConnectionRefusedError": "connection_refused",
        "ConnectionResetError": "connection_reset",
        "ConnectionAbortedError": "connection_aborted",
        "DNSError": "dns_error",
        "SSLError": "ssl_error",
        "CertificateError": "certificate_error",
        "AuthenticationError": "authentication_error",
        "PermissionError": "permission_denied",
        "FileNotFoundError": "not_found",
        "ValueError": "invalid_argument",
        "TypeError": "invalid_argument",
        "KeyError": "not_found",
        "IndexError": "out_of_range",
        "MemoryError": "resource_exhausted",
        "OSError": "system_error",
        "IOError": "io_error",
        "InterruptedError": "cancelled",
        "BrokenPipeError": "connection_broken",
        "NotImplementedError": "unimplemented",
    }

    # Check for HTTP status code errors (if error has status_code attribute)
    if hasattr(error, "status_code"):
        status_code = getattr(error, "status_code")
        if isinstance(status_code, int):
            return str(status_code)

    # Check for response attribute with status_code
    if hasattr(error, "response") and hasattr(error.response, "status_code"):
        status_code = getattr(error.response, "status_code")
        if isinstance(status_code, int):
            return str(status_code)

    # Use mapped error type if available, otherwise use class name
    return error_type_mapping.get(error_class, error_class)


def handle_rate_limit_error(
    span: trace.Span, response: object, operation_name: str, **request_context
) -> dict:
    """Handle rate limiting errors gracefully with proper span error attributes.

    Args:
        span: The span to add error attributes to
        response: HTTP response object (requests.Response or httpx.Response)
        operation_name: Name of the operation being rate limited
        **request_context: Additional request context (repo, query, etc.)

    Returns:
        Dictionary with error information for graceful handling
    """
    import time

    # Extract rate limit information from response headers
    rate_limit_info = {}

    # Common GitHub rate limit headers
    headers = getattr(response, "headers", {})
    if hasattr(headers, "get"):
        rate_limit_info.update(
            {
                "rate_limit_remaining": headers.get("x-ratelimit-remaining"),
                "rate_limit_limit": headers.get("x-ratelimit-limit"),
                "rate_limit_reset": headers.get("x-ratelimit-reset"),
                "rate_limit_used": headers.get("x-ratelimit-used"),
                "rate_limit_resource": headers.get("x-ratelimit-resource"),
                "retry_after": headers.get("retry-after"),
            }
        )

    # Calculate reset time if available
    reset_timestamp = rate_limit_info.get("rate_limit_reset")
    if reset_timestamp:
        try:
            reset_time = int(reset_timestamp)
            current_time = int(time.time())
            reset_in_seconds = max(0, reset_time - current_time)
            rate_limit_info["rate_limit_reset_in_seconds"] = reset_in_seconds
        except (ValueError, TypeError):
            pass

    # Add comprehensive rate limit attributes to span using semantic conventions
    status_code = getattr(response, "status_code", None)
    span.set_attribute(SpanAttributes.HTTP_RESPONSE_STATUS_CODE, status_code or 429)
    span.set_attribute(
        ERROR_TYPE, str(status_code or 429)
    )  # Use status code as error type
    span.set_attribute("error.rate_limit.operation", operation_name)
    span.set_attribute("error.rate_limit.status_code", str(status_code or 429))

    # Add rate limit specific attributes
    for key, value in rate_limit_info.items():
        if value is not None:
            span.set_attribute(f"error.rate_limit.{key}", str(value))

    # Add request context
    for key, value in request_context.items():
        if value is not None:
            span.set_attribute(f"error.rate_limit.request.{key}", str(value))

    # Create structured error message
    error_message = f"Rate limited for operation '{operation_name}'"
    if rate_limit_info.get("rate_limit_reset_in_seconds"):
        error_message += (
            f" (resets in {rate_limit_info['rate_limit_reset_in_seconds']}s)"
        )

    span.set_attribute(SpanAttributes.EXCEPTION_MESSAGE, error_message)

    # Set span status to error but don't record as exception since this is expected
    span.set_status(Status(StatusCode.ERROR, error_message))

    # Add span event for rate limiting
    span.add_event(
        "rate_limit_encountered",
        {
            "operation": operation_name,
            "status_code": status_code or 429,
            "remaining": rate_limit_info.get("rate_limit_remaining", "unknown"),
            "reset_in_seconds": rate_limit_info.get(
                "rate_limit_reset_in_seconds", "unknown"
            ),
            **{
                f"request_{k}": str(v)
                for k, v in request_context.items()
                if v is not None
            },
        },
    )

    # Return structured error information for graceful handling
    return {
        "error_type": "rate_limit",
        "message": error_message,
        "status_code": status_code or 429,
        "rate_limit_info": rate_limit_info,
        "request_context": request_context,
        "retry_recommended": True,
        "retry_after_seconds": rate_limit_info.get("rate_limit_reset_in_seconds") or 60,
    }


def add_mcp_operation_context(
    span: trace.Span,
    operation_type: str,
    operation_name: str,
    input_data: Optional[dict] = None,
    **context,
) -> None:
    """Add comprehensive MCP operation context to a span.

    Args:
        span: The span to add context to
        operation_type: Type of operation (tool, prompt, server)
        operation_name: Name of the specific operation
        input_data: Input data for the operation
        **context: Additional context attributes
    """
    import time
    import uuid

    # Generate unique operation ID for tracing
    operation_id = str(uuid.uuid4())

    # Core operation attributes
    span.set_attribute(MCPAttributes.MCP_OPERATION_ID, operation_id)
    span.set_attribute(MCPAttributes.MCP_OPERATION_TYPE, operation_type)
    span.set_attribute("operation.name", operation_name)
    span.set_attribute("operation.timestamp", int(time.time() * 1000))

    # Add input size if provided
    if input_data:
        input_size = len(str(input_data))
        if operation_type == "tool":
            span.set_attribute(MCPAttributes.MCP_TOOL_INPUT_SIZE, input_size)
        elif operation_type == "prompt":
            span.set_attribute(MCPAttributes.MCP_PROMPT_INPUT_SIZE, input_size)

    # Add session context
    session_id = extract_session_id_from_request()
    if session_id:
        span.set_attribute(MCPAttributes.MCP_SESSION_ID, session_id)

    # Add transport context
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    span.set_attribute(MCPAttributes.MCP_TRANSPORT, transport)

    # Add any additional context
    for key, value in context.items():
        if value is not None:
            span.set_attribute(f"mcp.context.{key}", str(value))


def add_operation_metrics(
    span: trace.Span,
    operation_type: str,
    start_time: float,
    output_data: Optional[dict] = None,
    **metrics,
) -> None:
    """Add operation performance metrics to a span.

    Args:
        span: The span to add metrics to
        operation_type: Type of operation (tool, prompt)
        start_time: Operation start time (from time.time())
        output_data: Output data for size calculation
        **metrics: Additional metrics to add
    """
    import time

    # Calculate execution time
    execution_time = int((time.time() - start_time) * 1000)  # Convert to milliseconds

    if operation_type == "tool":
        span.set_attribute(MCPAttributes.MCP_TOOL_EXECUTION_TIME, execution_time)
    elif operation_type == "prompt":
        span.set_attribute("mcp.prompt.execution_time_ms", execution_time)

    # Add output size if provided
    if output_data:
        output_size = len(str(output_data))
        if operation_type == "tool":
            span.set_attribute(MCPAttributes.MCP_TOOL_OUTPUT_SIZE, output_size)
        elif operation_type == "prompt":
            span.set_attribute(MCPAttributes.MCP_PROMPT_OUTPUT_SIZE, output_size)

    # Add custom metrics
    for key, value in metrics.items():
        if value is not None:
            span.set_attribute(f"metrics.{key}", value)


def create_span_event(event_name: str, operation_type: str, **event_data) -> dict:
    """Create a structured span event with consistent formatting.

    Args:
        event_name: Name of the event
        operation_type: Type of operation (tool, prompt, server)
        **event_data: Additional event data

    Returns:
        Dictionary with structured event data
    """
    import time

    event = {
        "event_type": operation_type,
        "timestamp": int(time.time() * 1000),
        **event_data,
    }

    # Add session context if available
    session_id = extract_session_id_from_request()
    if session_id:
        event["session_id"] = session_id

    return event


# MCP-specific semantic conventions
# Following OpenTelemetry naming conventions: https://opentelemetry.io/docs/specs/semconv/
class MCPAttributes:
    """MCP-specific span attributes following OpenTelemetry semantic conventions."""

    # MCP tool execution attributes
    MCP_TOOL_NAME = "mcp.tool.name"
    MCP_TOOL_ARGUMENTS = "mcp.tool.arguments"
    MCP_TOOL_CATEGORY = "mcp.tool.category"
    MCP_TOOL_EXECUTION_TIME = "mcp.tool.execution_time_ms"
    MCP_TOOL_INPUT_SIZE = "mcp.tool.input.size_bytes"
    MCP_TOOL_OUTPUT_SIZE = "mcp.tool.output.size_bytes"

    # MCP prompt attributes
    MCP_PROMPT_NAME = "mcp.prompt.name"
    MCP_PROMPT_ARGUMENTS = "mcp.prompt.arguments"
    MCP_PROMPT_CATEGORY = "mcp.prompt.category"
    MCP_PROMPT_INPUT_SIZE = "mcp.prompt.input.size_bytes"
    MCP_PROMPT_OUTPUT_SIZE = "mcp.prompt.output.size_bytes"

    # MCP server attributes
    MCP_TRANSPORT = "mcp.transport"

    # MCP session attributes for SSE connections
    MCP_SESSION_ID = "mcp.session.id"
    MCP_SESSION_TYPE = "mcp.session.type"
    MCP_SESSION_DURATION = "mcp.session.duration_ms"

    # MCP operation context
    MCP_OPERATION_ID = "mcp.operation.id"
    MCP_OPERATION_TYPE = "mcp.operation.type"
    MCP_OPERATION_CONTEXT = "mcp.operation.context"


# GenAI semantic conventions following OpenTelemetry specification
# These match the official OpenTelemetry GenAI semantic conventions spec:
# https://opentelemetry.io/docs/specs/semconv/gen-ai/
#
# Note: Official GenAI attributes are not yet available in the
# opentelemetry-semantic-conventions package, so we define them here
# following the official specification.
class GenAiAttributes:
    """GenAI span attributes following OpenTelemetry semantic conventions.

    Based on official OpenTelemetry GenAI semantic conventions:
    https://opentelemetry.io/docs/specs/semconv/gen-ai/

    These attributes follow the official specification and will be replaced
    with the official package attributes when they become available.
    """

    # GenAI system identification
    GEN_AI_SYSTEM = "gen_ai.system"

    # GenAI request attributes
    GEN_AI_REQUEST_MODEL = "gen_ai.request.model"

    # GenAI operation attributes
    GEN_AI_OPERATION_NAME = "gen_ai.operation.name"

    # GenAI usage/token attributes
    GEN_AI_USAGE_PROMPT_TOKENS = "gen_ai.usage.prompt_tokens"
    GEN_AI_USAGE_COMPLETION_TOKENS = "gen_ai.usage.completion_tokens"
    GEN_AI_USAGE_TOTAL_TOKENS = "gen_ai.usage.total_tokens"


# VCS semantic conventions following OpenTelemetry specification
# Based on official OpenTelemetry VCS semantic conventions:
# https://opentelemetry.io/docs/specs/semconv/registry/attributes/vcs/
class VCSAttributes:
    """VCS span attributes following OpenTelemetry semantic conventions."""

    # Repository identification
    VCS_REPOSITORY_NAME = "vcs.repository.name"
    VCS_REPOSITORY_URL_FULL = "vcs.repository.url.full"
    VCS_PROVIDER_NAME = "vcs.provider.name"
    VCS_OWNER_NAME = "vcs.owner.name"

    # Reference information (head = current, base = starting point)
    VCS_REF_HEAD_NAME = "vcs.ref.head.name"
    VCS_REF_HEAD_REVISION = "vcs.ref.head.revision"
    VCS_REF_HEAD_TYPE = "vcs.ref.head.type"
    VCS_REF_BASE_NAME = "vcs.ref.base.name"
    VCS_REF_BASE_REVISION = "vcs.ref.base.revision"
    VCS_REF_BASE_TYPE = "vcs.ref.base.type"

    # Change/PR information
    VCS_CHANGE_ID = "vcs.change.id"
    VCS_CHANGE_TITLE = "vcs.change.title"
    VCS_CHANGE_STATE = "vcs.change.state"


def extract_session_id_from_request() -> Optional[str]:
    """Extract session ID from current HTTP request context.

    This function attempts to extract the MCP session ID from:
    1. HTTP headers (mcp-session-id, x-session-id)
    2. Query parameters (session_id)
    3. Environment variables (for stdio transport)

    Returns:
        Optional session ID string, or None if not found
    """
    try:
        # For SSE transport, try to get session from FastMCP context
        from fastmcp.server.http import _current_http_request

        request = _current_http_request.get(None)
        if request is not None:
            # Check for session ID in headers (multiple possible header names)
            for header_name in ["mcp-session-id", "x-session-id", "session-id"]:
                session_id = request.headers.get(header_name)
                if session_id:
                    return session_id

            # Check query parameters as fallback
            session_id = request.query_params.get("session_id")
            if session_id:
                return session_id

        # For stdio transport, generate a consistent session ID
        transport = os.getenv("MCP_TRANSPORT", "stdio")
        if transport == "stdio":
            # Use process ID as session identifier for stdio
            return f"stdio-{os.getpid()}"

        return None
    except Exception:
        # Silently fail if we can't extract session ID
        # For stdio transport, still provide a session ID
        transport = os.getenv("MCP_TRANSPORT", "stdio")
        if transport == "stdio":
            return f"stdio-{os.getpid()}"
        return None


# Removed create_session_aware_root_span_context - replaced with direct session extraction
# in MCP tools for better control and clarity
