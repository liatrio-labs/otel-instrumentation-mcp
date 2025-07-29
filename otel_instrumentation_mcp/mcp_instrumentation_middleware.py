"""Custom instrumentation middleware for MCP operations.

This module provides selective instrumentation for MCP operations,
avoiding noisy traces from internal SSE communication while providing
meaningful observability for actual MCP tool and prompt executions.
"""

import logging
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from opentelemetry.semconv.trace import SpanAttributes

from otel_instrumentation_mcp.telemetry import (
    get_tracer,
    get_logger,
    MCPAttributes,
    add_span_attributes,
)

logger = get_logger()
tracer = get_tracer()


class MCPInstrumentationMiddleware(BaseHTTPMiddleware):
    """Custom middleware for selective MCP instrumentation.

    This middleware:
    1. Creates root spans only for meaningful MCP operations
    2. Extracts and tracks session IDs from SSE connections
    3. Excludes internal SSE POST messages from instrumentation
    4. Provides proper session context for all MCP operations
    """

    def __init__(self, app, excluded_paths: Optional[list[str]] = None):
        super().__init__(app)
        self.excluded_paths = excluded_paths or [
            "/health",
            "/ready",
            "/sse",  # SSE endpoint - internal communication
            "/mcp",  # MCP internal endpoints
        ]

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with selective MCP instrumentation."""

        # Skip instrumentation for excluded paths
        if self._should_exclude_path(request.url.path):
            return await call_next(request)

        # Extract session information
        session_id = self._extract_session_id(request)
        transport_type = self._detect_transport_type(request)

        # Create root span for MCP operations only
        if self._is_mcp_operation(request):
            operation_name = self._get_operation_name(request)

            with tracer.start_as_current_span(
                name=operation_name,
                attributes=self._build_span_attributes(
                    request, session_id, transport_type, operation_name
                ),
            ) as span:
                try:
                    response = await call_next(request)

                    # Add response attributes using semantic conventions
                    response_attributes = {
                        SpanAttributes.HTTP_RESPONSE_STATUS_CODE: response.status_code,
                    }

                    # Add response size if available
                    if hasattr(response, "body") and response.body:
                        response_attributes["http.response.body.size"] = len(
                            response.body
                        )

                    add_span_attributes(span, **response_attributes)

                    # Set span status based on HTTP semantic conventions
                    if response.status_code >= 400:
                        if response.status_code >= 500:
                            # 5xx errors are always errors
                            span.set_status(
                                Status(StatusCode.ERROR, f"HTTP {response.status_code}")
                            )
                        # 4xx errors: leave unset for server spans (this is server-side middleware)
                    else:
                        # 1xx, 2xx, 3xx: leave unset (OK)
                        pass

                    return response

                except Exception as e:
                    # Set error attributes following semantic conventions
                    error_type = e.__class__.__name__
                    span.set_attribute("error.type", error_type)
                    span.set_attribute(SpanAttributes.EXCEPTION_MESSAGE, str(e))
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    logger.error(
                        f"MCP operation failed: {operation_name}",
                        exc_info=True,
                        extra={
                            "session_id": session_id,
                            "transport": transport_type,
                            "operation": operation_name,
                            "error_type": error_type,
                        },
                    )
                    raise
        else:
            # Non-MCP operations - pass through without instrumentation
            return await call_next(request)

    def _should_exclude_path(self, path: str) -> bool:
        """Check if path should be excluded from instrumentation."""
        return any(path.startswith(excluded) for excluded in self.excluded_paths)

    def _extract_session_id(self, request: Request) -> Optional[str]:
        """Extract session ID from request headers or query parameters."""
        # Check headers first (preferred for SSE)
        session_id = request.headers.get("mcp-session-id")
        if session_id:
            return session_id

        # Check query parameters (used in SSE POST messages)
        session_id = request.query_params.get("session_id")
        if session_id:
            return session_id

        return None

    def _detect_transport_type(self, request: Request) -> str:
        """Detect the MCP transport type from request characteristics."""
        # Check for SSE-specific headers
        if request.headers.get("accept") == "text/event-stream":
            return "sse"

        # Check for MCP session headers
        if request.headers.get("mcp-session-id"):
            return "sse"

        # Check for session_id in query params (SSE POST messages)
        if request.query_params.get("session_id"):
            return "sse"

        # Check path patterns
        if "/sse" in request.url.path:
            return "sse"
        elif "/mcp" in request.url.path:
            return "http"

        return "stdio"  # Default fallback

    def _is_mcp_operation(self, request: Request) -> bool:
        """Determine if this is a meaningful MCP operation to instrument."""
        path = request.url.path

        # Direct HTTP endpoints for tools (these are meaningful)
        mcp_endpoints = ["/repos", "/issues", "/examples", "/demo", "/otel-docs"]

        if any(endpoint in path for endpoint in mcp_endpoints):
            return True

        # SSE GET requests (establishing connection)
        if request.method == "GET" and "/sse" in path:
            return True

        # MCP HTTP transport requests
        if "/mcp" in path and request.method == "POST":
            return True

        return False

    def _get_operation_name(self, request: Request) -> str:
        """Generate a meaningful operation name following HTTP semantic conventions for HTTP transport."""
        path = request.url.path
        method = request.method
        transport_type = self._detect_transport_type(request)

        # For HTTP/SSE transport, use HTTP semantic convention naming
        if transport_type in ["http", "sse"]:
            # Use HTTP method + path pattern for HTTP spans
            # Map specific endpoints to low-cardinality path templates
            path_templates = {
                "/repos": "/repos",
                "/issues": "/issues",
                "/issues/search": "/issues/search",
                "/examples": "/examples",
                "/demo": "/demo",
                "/otel-docs": "/otel-docs",
                "/sse": "/sse",
                "/mcp": "/mcp",
            }

            # Find matching path template
            path_template = path
            for endpoint, template in path_templates.items():
                if endpoint in path:
                    path_template = template
                    break

            return f"{method} {path_template}"

        # For stdio transport, use MCP-specific naming
        endpoint_mapping = {
            "/repos": "mcp.tool.list_opentelemetry_repos",
            "/issues": "mcp.tool.list_opentelemetry_issues",
            "/issues/search": "mcp.tool.search_opentelemetry_issues",
            "/examples": "mcp.tool.get_opentelemetry_examples",
            "/demo": "mcp.tool.get_opentelemetry_examples_by_language",
            "/otel-docs": "mcp.tool.get_opentelemetry_docs_by_language",
        }

        for endpoint, operation in endpoint_mapping.items():
            if endpoint in path:
                return operation

        # Fallback for other operations
        if "/sse" in path and method == "GET":
            return "mcp.session.sse_connect"
        elif "/mcp" in path:
            return "mcp.transport.http_request"
        else:
            return f"mcp.operation.{method.lower()}_{path.replace('/', '_').strip('_')}"

    def _build_span_attributes(
        self,
        request: Request,
        session_id: Optional[str],
        transport_type: str,
        operation_name: str,
    ) -> dict:
        """Build comprehensive span attributes for MCP operations following OpenTelemetry semantic conventions."""
        attributes = {
            # Standard HTTP attributes (stable semantic conventions)
            SpanAttributes.HTTP_REQUEST_METHOD: request.method,
            SpanAttributes.URL_FULL: str(request.url),
            SpanAttributes.URL_SCHEME: request.url.scheme,
            SpanAttributes.URL_PATH: request.url.path,
            SpanAttributes.SERVER_ADDRESS: request.url.hostname or "localhost",
            # MCP-specific attributes (custom namespace)
            MCPAttributes.MCP_TRANSPORT: transport_type,
            "mcp.operation": operation_name,
            "operation.type": "mcp",
        }

        # Add server port if available
        if request.url.port:
            attributes[SpanAttributes.SERVER_PORT] = request.url.port

        # Add network attributes for HTTP/SSE transport
        if transport_type in ["http", "sse"]:
            attributes.update(
                {
                    SpanAttributes.NETWORK_PROTOCOL_NAME: "http",
                    SpanAttributes.NETWORK_PROTOCOL_VERSION: "1.1",  # Default, could be detected
                    SpanAttributes.NETWORK_TRANSPORT: "tcp",
                }
            )

        # Add session tracking for SSE
        if session_id:
            attributes[MCPAttributes.MCP_SESSION_ID] = session_id
            attributes[MCPAttributes.MCP_SESSION_TYPE] = transport_type

        # Add query parameters if present
        if request.query_params:
            for key, value in request.query_params.items():
                if key != "session_id":  # Don't duplicate session_id
                    attributes[f"http.query.{key}"] = value

        return attributes
