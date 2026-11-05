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
            "/ready",
            # Note: We don't exclude /health and /cache/status as these should be instrumented
            # Note: We don't exclude /sse and /mcp as these are handled by _is_mcp_operation
        ]

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with selective MCP instrumentation and client IP capture."""
        import contextvars
        from opentelemetry import trace

        # Extract client IP for all requests
        client_ip = self._extract_client_ip(request)
        
        # Store client IP in request state for manual spans to access
        if client_ip:
            request.state.client_ip = client_ip
        
        # Store request in context variable for telemetry functions to access
        request_context = contextvars.ContextVar("current_request", default=None)
        request_context.set(request)

        # Add client IP to any existing span in the current context
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording() and client_ip:
            current_span.set_attribute("source.address", client_ip)
            current_span.set_attribute("http.client_ip", client_ip)

        # Check if this is a meaningful MCP operation that should be instrumented
        if self._is_mcp_operation(request) and not self._should_exclude_path(request.url.path):
            # Create a root span for this MCP operation
            session_id = self._extract_session_id(request)
            transport_type = self._detect_transport_type(request)
            operation_name = self._get_operation_name(request)
            
            with tracer.start_as_current_span(operation_name) as span:
                # Build comprehensive span attributes including client IP
                attributes = self._build_span_attributes(
                    request, session_id, transport_type, operation_name, client_ip
                )
                span.set_attributes(attributes)
                
                # Add span event for request start
                span.add_event("http_request_started", {
                    "http.method": request.method,
                    "http.url": str(request.url),
                    "client.ip": client_ip or "unknown",
                    "transport.type": transport_type,
                })
                
                try:
                    # Process the request
                    response = await call_next(request)
                    
                    # Add response attributes
                    span.set_attributes({
                        SpanAttributes.HTTP_RESPONSE_STATUS_CODE: response.status_code,
                    })
                    
                    # Set span status based on HTTP status
                    if response.status_code >= 400:
                        span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
                    else:
                        span.set_status(Status(StatusCode.OK))
                    
                    # Add completion event
                    span.add_event("http_request_completed", {
                        "http.status_code": response.status_code,
                        "response.success": response.status_code < 400,
                    })
                    
                    return response
                    
                except Exception as e:
                    # Handle errors
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attributes({
                        SpanAttributes.ERROR_TYPE: e.__class__.__name__,
                        "error.message": str(e),
                    })
                    span.add_event("http_request_failed", {
                        "error.type": e.__class__.__name__,
                        "error.message": str(e),
                    })
                    raise
        else:
            # For non-MCP operations, just pass through
            # But still try to add client IP to any existing span
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording() and client_ip:
                current_span.set_attributes({
                    "source.address": client_ip,
                    "http.client_ip": client_ip,
                })
            
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

    def _extract_client_ip(self, request: Request) -> Optional[str]:
        """Extract the real client IP address from various headers and sources."""
        # Check X-Forwarded-For header first (most common for load balancers)
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            # X-Forwarded-For can contain multiple IPs, take the first one
            ips = [ip.strip() for ip in xff.split(",")]
            if ips and ips[0] and ips[0] != "unknown":
                return ips[0]
        
        # Check X-Real-IP header
        xri = request.headers.get("X-Real-IP")
        if xri and xri != "unknown":
            return xri
        
        # Check CF-Connecting-IP (Cloudflare)
        cfip = request.headers.get("CF-Connecting-IP")
        if cfip and cfip != "unknown":
            return cfip
        
        # Check X-Forwarded-Proto and other common proxy headers
        forwarded = request.headers.get("Forwarded")
        if forwarded:
            # Parse RFC 7239 Forwarded header: for=192.0.2.60;proto=http;by=203.0.113.43
            for part in forwarded.split(";"):
                if part.strip().startswith("for="):
                    ip = part.strip()[4:].strip('"')
                    if ip and ip != "unknown":
                        return ip
        
        # Fall back to client address from request
        if hasattr(request, "client") and request.client:
            return request.client.host
        
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

        # Direct HTTP endpoints that exist
        direct_endpoints = ["/health", "/cache/status"]

        if any(path.startswith(endpoint) for endpoint in direct_endpoints):
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
                "/health": "/health",
                "/cache/status": "/cache/status",
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
            "/health": "mcp.health.check",
            "/cache/status": "mcp.cache.status",
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
        client_ip: Optional[str] = None,
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

        # Add client IP for GeoIP processing
        if client_ip:
            attributes["source.address"] = client_ip
            attributes["http.client_ip"] = client_ip

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
