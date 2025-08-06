#!/usr/bin/env python3
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

"""OpenTelemetry Instrumentation MCP Server."""

import asyncio
import logging
import os
import signal
import sys
import uvicorn
from fastmcp import FastMCP
from fastapi import FastAPI
from starlette.routing import Mount, Route
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Status, StatusCode

from otel_instrumentation_mcp.telemetry import (
    telemetry,
    get_tracer,
    get_logger,
    set_span_error,
    add_span_attributes,
    create_root_span_context,
    extract_session_id_from_request,
    add_enhanced_error_attributes,
    add_mcp_operation_context,
    add_operation_metrics,
    create_span_event,
    MCPAttributes,
    GenAiAttributes,
)
from otel_instrumentation_mcp.opentelemetry_repos import get_opentelemetry_repos
from otel_instrumentation_mcp.github_issues import get_repo_issues, search_repo_issues
from otel_instrumentation_mcp.opentelemetry_examples import (
    get_demo_services_doc,
    get_demo_services_by_language,
)
from otel_instrumentation_mcp.opentelemetry_docs import get_docs_by_language
from otel_instrumentation_mcp.semantic_conventions import (
    get_semantic_conventions as fetch_semantic_conventions,
)
from otel_instrumentation_mcp.instrumentation_score import (
    fetch_instrumentation_score_specification,
    fetch_instrumentation_score_rules,
)
from otel_instrumentation_mcp.instrumentation_score_prompt import (
    instrumentation_score_analysis_prompt as instrumentation_score_analysis_prompt_func,
)
from otel_instrumentation_mcp.code_analysis_prompt import (
    ask_about_code as ask_about_code_func,
)
from otel_instrumentation_mcp.custom_instrumentation_prompt import (
    custom_instrumentation_prompt as custom_instrumentation_prompt_func,
)
from otel_instrumentation_mcp.autoinstrumentation_prompt import (
    autoinstrumentation_prompt as autoinstrumentation_prompt_func,
)
from otel_instrumentation_mcp.network_utils import (
    get_optimal_host_binding,
    validate_host_binding,
)
from fastmcp.prompts.prompt import Message, PromptMessage, TextContent

# Initialize OpenTelemetry
telemetry.initialize()

# Get instrumented logger and tracer
logger = get_logger()
tracer = get_tracer()


# Initialize MCP server with tracing
with tracer.start_as_current_span("mcp.server.initialize") as span:
    logger.info("Initializing MCP server")
    mcp = FastMCP("Opentelemetry Instrumentation")

    # Create the ASGI apps for both HTTP and SSE transports
    mcp_http_app = mcp.http_app(path="/", transport="http")
    mcp_sse_app = mcp.sse_app(path="/")

    # Create a FastAPI app and mount both MCP servers
    app = FastAPI(
        title="OpenTelemetry Instrumentation MCP Server",
        description="MCP server for OpenTelemetry instrumentation assistance",
        lifespan=mcp_http_app.lifespan,
    )

    # No middleware needed - all instrumentation is handled manually in MCP tools
    # This eliminates noise from HTTP transport layers and SSE internal requests

    logger.info("MCP server initialized successfully")


@mcp.prompt
async def ask_about_code(code_snippet: str) -> PromptMessage:
    """Ask a question about a code snippet.

    Generates a user message asking for analysis and OpenTelemetry documentation for a code snippet.

    Args:
        code_snippet: The code snippet to analyze and find documentation for

    Returns:
        PromptMessage: A formatted message containing the analysis request
    """
    import time

    start_time = time.time()

    # Create true root span for this MCP prompt operation with session tracking
    session_id = extract_session_id_from_request()
    with create_root_span_context(
        tracer, "mcp.prompt.ask_about_code", "prompt", session_id
    ) as span:
        try:
            # Add comprehensive MCP operation context
            input_data = {"code_snippet": code_snippet}
            add_mcp_operation_context(
                span,
                operation_type="prompt",
                operation_name="ask_about_code",
                input_data=input_data,
                prompt_category="code_analysis",
                language_detection="auto",
            )

            # Add GenAI specific attributes
            add_span_attributes(
                span,
                **{
                    GenAiAttributes.GEN_AI_SYSTEM: "opentelemetry-mcp",
                    GenAiAttributes.GEN_AI_OPERATION_NAME: "code_analysis",
                    SpanAttributes.CODE_FUNCTION: "ask_about_code",
                    MCPAttributes.MCP_PROMPT_CATEGORY: "code_analysis",
                },
            )

            # Add structured span event for prompt start
            span.add_event(
                "prompt_processing_started",
                create_span_event(
                    "prompt_processing_started",
                    "prompt",
                    prompt_name="ask_about_code",
                    input_size_bytes=len(code_snippet),
                    code_lines=len(code_snippet.split("\n")),
                    estimated_complexity="medium",
                ),
            )

            logger.info(
                "Generating code analysis prompt",
                extra={
                    "code_snippet_length": len(code_snippet),
                    "prompt_type": "ask_about_code",
                    "session_id": session_id,
                    "code_lines": len(code_snippet.split("\n")),
                },
            )

            message = ask_about_code_func(code_snippet)

            # Enhanced token tracking with more detailed metrics
            estimated_input_tokens = len(code_snippet.split()) * 1.3
            estimated_output_tokens = len(message.split()) * 1.3
            total_tokens = estimated_input_tokens + estimated_output_tokens

            # Add operation metrics
            output_data = {"message": message}
            add_operation_metrics(
                span,
                operation_type="prompt",
                start_time=start_time,
                output_data=output_data,
                input_tokens=int(estimated_input_tokens),
                output_tokens=int(estimated_output_tokens),
                total_tokens=int(total_tokens),
                code_lines_processed=len(code_snippet.split("\n")),
                message_length=len(message),
            )

            # Add GenAI token attributes
            add_span_attributes(
                span,
                **{
                    GenAiAttributes.GEN_AI_USAGE_PROMPT_TOKENS: int(
                        estimated_input_tokens
                    ),
                    GenAiAttributes.GEN_AI_USAGE_COMPLETION_TOKENS: int(
                        estimated_output_tokens
                    ),
                    GenAiAttributes.GEN_AI_USAGE_TOTAL_TOKENS: int(total_tokens),
                },
            )

            # Add generated prompt as span event with MCP and GenAI semantic conventions
            span.add_event(
                "prompt_content_generated",
                {
                    # MCP semantic conventions
                    MCPAttributes.MCP_PROMPT_NAME: "ask_about_code",
                    MCPAttributes.MCP_PROMPT_CATEGORY: "code_analysis",
                    MCPAttributes.MCP_PROMPT_OUTPUT_SIZE: len(message),
                    # GenAI semantic conventions
                    GenAiAttributes.GEN_AI_SYSTEM: "opentelemetry-mcp",
                    GenAiAttributes.GEN_AI_OPERATION_NAME: "code_analysis",
                    GenAiAttributes.GEN_AI_USAGE_PROMPT_TOKENS: int(
                        estimated_input_tokens
                    ),
                    GenAiAttributes.GEN_AI_USAGE_COMPLETION_TOKENS: int(
                        estimated_output_tokens
                    ),
                    GenAiAttributes.GEN_AI_USAGE_TOTAL_TOKENS: int(total_tokens),
                    "prompt.content": message,
                    "prompt.content.length": len(message),
                    "prompt.content.lines": len(message.split("\n")),
                    "prompt.input.code_snippet_length": len(code_snippet),
                    "prompt.input.code_lines": len(code_snippet.split("\n")),
                    "processing_time_ms": int((time.time() - start_time) * 1000),
                    "timestamp": int(time.time() * 1000),
                },
            )

            # Add detailed completion event
            span.add_event(
                "prompt_generated",
                create_span_event(
                    "prompt_generated",
                    "prompt",
                    prompt_name="ask_about_code",
                    message_length=len(message),
                    estimated_input_tokens=int(estimated_input_tokens),
                    estimated_output_tokens=int(estimated_output_tokens),
                    total_tokens=int(total_tokens),
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    success=True,
                ),
            )

            span.set_status(Status(StatusCode.OK))

            return PromptMessage(
                role="user",
                content=TextContent(type="text", text=message),
                messages=[
                    Message(role="user", content=TextContent(type="text", text=message))
                ],
            )
        except Exception as e:
            # Enhanced error tracking with operation context
            add_enhanced_error_attributes(
                span,
                e,
                code_snippet_length=len(code_snippet) if code_snippet else 0,
                operation="code_analysis",
                prompt_name="ask_about_code",
                session_id=session_id,
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

            # Add error event
            span.add_event(
                "prompt_generation_failed",
                create_span_event(
                    "prompt_generation_failed",
                    "prompt",
                    prompt_name="ask_about_code",
                    error_type=e.__class__.__name__,
                    error_message=str(e),
                    code_snippet_length=len(code_snippet) if code_snippet else 0,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                ),
            )

            logger.error(
                "Failed to generate code analysis prompt",
                exc_info=True,
                extra={
                    "error_type": e.__class__.__name__,
                    "code_snippet_length": len(code_snippet) if code_snippet else 0,
                    "session_id": session_id,
                    "processing_time_ms": int((time.time() - start_time) * 1000),
                },
            )
            raise


@mcp.prompt
async def autoinstrumentation_prompt(code_snippet: str) -> PromptMessage:
    """Ask a question about a code snippet.

    Generates a user message asking for autoinstrumentation updates to the code snippet.

    Args:
        code_snippet: The code snippet to analyze and find documentation for

    Returns:
        PromptMessage: A formatted message containing the autoinstrumentation request
    """
    import time

    session_id = extract_session_id_from_request()
    with create_root_span_context(
        tracer, "mcp.prompt.autoinstrumentation", "prompt", session_id
    ) as span:
        try:
            add_span_attributes(
                span,
                **{
                    MCPAttributes.MCP_PROMPT_NAME: "autoinstrumentation_prompt",
                    MCPAttributes.MCP_PROMPT_ARGUMENTS: f"code_snippet_length={len(code_snippet)}",
                    GenAiAttributes.GEN_AI_SYSTEM: "opentelemetry-mcp",
                    GenAiAttributes.GEN_AI_OPERATION_NAME: "autoinstrumentation_guidance",
                    SpanAttributes.CODE_FUNCTION: "autoinstrumentation_prompt",
                },
            )

            logger.info(
                "Generating autoinstrumentation prompt",
                extra={
                    "code_snippet_length": len(code_snippet),
                    "prompt_type": "autoinstrumentation",
                },
            )

            message = autoinstrumentation_prompt_func(code_snippet)

            estimated_input_tokens = len(code_snippet.split()) * 1.3
            estimated_output_tokens = len(message.split()) * 1.3
            total_tokens = estimated_input_tokens + estimated_output_tokens

            add_span_attributes(
                span,
                **{
                    GenAiAttributes.GEN_AI_USAGE_PROMPT_TOKENS: int(
                        estimated_input_tokens
                    ),
                    GenAiAttributes.GEN_AI_USAGE_COMPLETION_TOKENS: int(
                        estimated_output_tokens
                    ),
                    GenAiAttributes.GEN_AI_USAGE_TOTAL_TOKENS: int(total_tokens),
                },
            )

            # Add generated prompt as span event with MCP and GenAI semantic conventions
            span.add_event(
                "prompt_content_generated",
                {
                    # MCP semantic conventions
                    MCPAttributes.MCP_PROMPT_NAME: "autoinstrumentation_prompt",
                    MCPAttributes.MCP_PROMPT_CATEGORY: "autoinstrumentation",
                    MCPAttributes.MCP_PROMPT_OUTPUT_SIZE: len(message),
                    # GenAI semantic conventions
                    GenAiAttributes.GEN_AI_SYSTEM: "opentelemetry-mcp",
                    GenAiAttributes.GEN_AI_OPERATION_NAME: "autoinstrumentation_guidance",
                    GenAiAttributes.GEN_AI_USAGE_PROMPT_TOKENS: int(
                        estimated_input_tokens
                    ),
                    GenAiAttributes.GEN_AI_USAGE_COMPLETION_TOKENS: int(
                        estimated_output_tokens
                    ),
                    GenAiAttributes.GEN_AI_USAGE_TOTAL_TOKENS: int(total_tokens),
                    # Prompt content
                    "prompt.content": message,
                    "prompt.content.length": len(message),
                    "prompt.content.lines": len(message.split("\n")),
                    "prompt.input.code_snippet_length": len(code_snippet),
                    "prompt.input.code_lines": len(code_snippet.split("\n")),
                    # Processing metadata
                    "timestamp": int(time.time() * 1000),
                },
            )

            span.add_event(
                "prompt_generated",
                {
                    "message_length": len(message),
                    "estimated_input_tokens": int(estimated_input_tokens),
                    "estimated_output_tokens": int(estimated_output_tokens),
                    "total_tokens": int(total_tokens),
                },
            )

            return PromptMessage(
                role="user",
                content=TextContent(type="text", text=message),
                messages=[
                    Message(role="user", content=TextContent(type="text", text=message))
                ],
            )
        except Exception as e:
            set_span_error(span, e)
            logger.error("Failed to generate autoinstrumentation prompt", exc_info=True)
            raise


@mcp.prompt
async def custom_instrumentation_prompt(code_snippet: str) -> PromptMessage:
    """Ask a question about a code snippet.

    Generates a user message asking for custom instrumentation updates to the code snippet.

    Args:
        code_snippet: The code snippet to analyze and find documentation for

    Returns:
        PromptMessage: A formatted message containing the custom instrumentation request
    """
    import time

    session_id = extract_session_id_from_request()
    with create_root_span_context(
        tracer, "mcp.prompt.custom_instrumentation", "prompt", session_id
    ) as span:
        try:
            add_span_attributes(
                span,
                **{
                    MCPAttributes.MCP_PROMPT_NAME: "custom_instrumentation_prompt",
                    MCPAttributes.MCP_PROMPT_ARGUMENTS: f"code_snippet_length={len(code_snippet)}",
                    GenAiAttributes.GEN_AI_SYSTEM: "opentelemetry-mcp",
                    GenAiAttributes.GEN_AI_OPERATION_NAME: "custom_instrumentation_guidance",
                    SpanAttributes.CODE_FUNCTION: "custom_instrumentation_prompt",
                },
            )

            logger.info(
                "Generating custom instrumentation prompt",
                extra={
                    "code_snippet_length": len(code_snippet),
                    "prompt_type": "custom_instrumentation",
                },
            )

            message = custom_instrumentation_prompt_func(code_snippet)

            estimated_input_tokens = len(code_snippet.split()) * 1.3
            estimated_output_tokens = len(message.split()) * 1.3
            total_tokens = estimated_input_tokens + estimated_output_tokens

            add_span_attributes(
                span,
                **{
                    GenAiAttributes.GEN_AI_USAGE_PROMPT_TOKENS: int(
                        estimated_input_tokens
                    ),
                    GenAiAttributes.GEN_AI_USAGE_COMPLETION_TOKENS: int(
                        estimated_output_tokens
                    ),
                    GenAiAttributes.GEN_AI_USAGE_TOTAL_TOKENS: int(total_tokens),
                },
            )

            # Add generated prompt as span event with MCP and GenAI semantic conventions
            span.add_event(
                "prompt_content_generated",
                {
                    # MCP semantic conventions
                    MCPAttributes.MCP_PROMPT_NAME: "custom_instrumentation_prompt",
                    MCPAttributes.MCP_PROMPT_CATEGORY: "custom_instrumentation",
                    MCPAttributes.MCP_PROMPT_OUTPUT_SIZE: len(message),
                    # GenAI semantic conventions
                    GenAiAttributes.GEN_AI_SYSTEM: "opentelemetry-mcp",
                    GenAiAttributes.GEN_AI_OPERATION_NAME: "custom_instrumentation_guidance",
                    GenAiAttributes.GEN_AI_USAGE_PROMPT_TOKENS: int(
                        estimated_input_tokens
                    ),
                    GenAiAttributes.GEN_AI_USAGE_COMPLETION_TOKENS: int(
                        estimated_output_tokens
                    ),
                    GenAiAttributes.GEN_AI_USAGE_TOTAL_TOKENS: int(total_tokens),
                    # Prompt content
                    "prompt.content": message,
                    "prompt.content.length": len(message),
                    "prompt.content.lines": len(message.split("\n")),
                    "prompt.input.code_snippet_length": len(code_snippet),
                    "prompt.input.code_lines": len(code_snippet.split("\n")),
                    # Processing metadata
                    "timestamp": int(time.time() * 1000),
                },
            )

            span.add_event(
                "prompt_generated",
                {
                    "message_length": len(message),
                    "estimated_input_tokens": int(estimated_input_tokens),
                    "estimated_output_tokens": int(estimated_output_tokens),
                    "total_tokens": int(total_tokens),
                },
            )

            return PromptMessage(
                role="user",
                content=TextContent(type="text", text=message),
                messages=[
                    Message(role="user", content=TextContent(type="text", text=message))
                ],
            )
        except Exception as e:
            set_span_error(span, e)
            logger.error(
                "Failed to generate custom instrumentation prompt", exc_info=True
            )
            raise


@mcp.prompt
async def instrumentation_score_analysis_prompt(
    telemetry_data: str = "", service_name: str = "", focus_areas: str = ""
) -> PromptMessage:
    """Analyze instrumentation quality using the Instrumentation Score specification.

    Generates a user message asking for instrumentation quality analysis based on
    the Instrumentation Score rules and best practices.

    Args:
        telemetry_data: Optional telemetry data (traces, metrics, logs) to analyze
        service_name: Optional service name to focus the analysis on
        focus_areas: Optional comma-separated focus areas (e.g., "traces,metrics,resource_attributes")

    Returns:
        PromptMessage: A formatted message containing the instrumentation analysis request
    """
    import time

    session_id = extract_session_id_from_request()
    with create_root_span_context(
        tracer, "mcp.prompt.instrumentation_score_analysis", "prompt", session_id
    ) as span:
        try:
            add_span_attributes(
                span,
                **{
                    MCPAttributes.MCP_PROMPT_NAME: "instrumentation_score_analysis_prompt",
                    MCPAttributes.MCP_PROMPT_ARGUMENTS: f"service_name={service_name}, focus_areas={focus_areas}",
                    GenAiAttributes.GEN_AI_SYSTEM: "opentelemetry-mcp",
                    GenAiAttributes.GEN_AI_OPERATION_NAME: "instrumentation_quality_analysis",
                    SpanAttributes.CODE_FUNCTION: "instrumentation_score_analysis_prompt",
                },
            )

            logger.info(
                "Generating instrumentation score analysis prompt",
                extra={
                    "service_name": service_name,
                    "focus_areas": focus_areas,
                    "has_telemetry_data": bool(telemetry_data),
                    "prompt_type": "instrumentation_score_analysis",
                },
            )

            message = instrumentation_score_analysis_prompt_func(
                telemetry_data=telemetry_data,
                service_name=service_name,
                focus_areas=focus_areas,
            )

            estimated_input_tokens = (
                len(f"{telemetry_data} {service_name} {focus_areas}".split()) * 1.3
            )
            estimated_output_tokens = len(message.split()) * 1.3
            total_tokens = estimated_input_tokens + estimated_output_tokens

            add_span_attributes(
                span,
                **{
                    GenAiAttributes.GEN_AI_USAGE_PROMPT_TOKENS: int(
                        estimated_input_tokens
                    ),
                    GenAiAttributes.GEN_AI_USAGE_COMPLETION_TOKENS: int(
                        estimated_output_tokens
                    ),
                    GenAiAttributes.GEN_AI_USAGE_TOTAL_TOKENS: int(total_tokens),
                },
            )

            span.add_event(
                "prompt_generated",
                {
                    "message_length": len(message),
                    "estimated_input_tokens": int(estimated_input_tokens),
                    "estimated_output_tokens": int(estimated_output_tokens),
                    "total_tokens": int(total_tokens),
                },
            )

            return PromptMessage(
                role="user",
                content=TextContent(type="text", text=message),
                messages=[
                    Message(role="user", content=TextContent(type="text", text=message))
                ],
            )
        except Exception as e:
            set_span_error(span, e)
            logger.error(
                "Failed to generate instrumentation score analysis prompt",
                exc_info=True,
            )
            raise


@mcp.tool
async def list_opentelemetry_repos():
    """List OpenTelemetry repositories

    Returns a list of OpenTelemetry repositories
    """
    import time

    start_time = time.time()

    # Create true root span for this MCP tool operation with session tracking
    session_id = extract_session_id_from_request()
    with create_root_span_context(
        tracer, "mcp.tool.list_opentelemetry_repos", "tool", session_id
    ) as span:
        try:
            # Add comprehensive MCP operation context
            add_mcp_operation_context(
                span,
                operation_type="tool",
                operation_name="list_opentelemetry_repos",
                input_data={},
                tool_category="repository_management",
                data_source="static_list",
                cache_enabled=False,
            )

            # Add tool-specific attributes
            add_span_attributes(
                span,
                **{
                    SpanAttributes.CODE_FUNCTION: "list_opentelemetry_repos",
                    MCPAttributes.MCP_TOOL_CATEGORY: "repository_management",
                    "data.source": "opentelemetry_repos.py",
                    "operation.complexity": "low",
                },
            )

            # Add structured span event for tool start
            span.add_event(
                "tool_execution_started",
                create_span_event(
                    "tool_execution_started",
                    "tool",
                    tool_name="list_opentelemetry_repos",
                    expected_operation="fetch_static_repository_list",
                    cache_strategy="none",
                ),
            )

            logger.info(
                "Fetching OpenTelemetry repositories list",
                extra={
                    "session_id": session_id,
                    "operation": "list_repos",
                    "tool_category": "repository_management",
                },
            )

            repositories = get_opentelemetry_repos()

            # Add operation metrics with detailed results
            output_data = {"repositories": repositories}
            add_operation_metrics(
                span,
                operation_type="tool",
                start_time=start_time,
                output_data=output_data,
                repositories_count=len(repositories),
                data_freshness="static",
                result_size_bytes=len(str(repositories)),
            )

            # Add comprehensive result attributes
            add_span_attributes(
                span,
                **{
                    "repositories.count": len(repositories),
                    "result.success": True,
                    "result.type": "repository_list",
                    "data.freshness": "static",
                    "performance.category": (
                        "fast" if (time.time() - start_time) < 0.1 else "normal"
                    ),
                },
            )

            # Add detailed completion event
            span.add_event(
                "repositories_fetched",
                create_span_event(
                    "repositories_fetched",
                    "tool",
                    tool_name="list_opentelemetry_repos",
                    count=len(repositories),
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    result_size_bytes=len(str(repositories)),
                    success=True,
                    data_source="static_list",
                ),
            )

            logger.info(
                "Successfully fetched repositories",
                extra={
                    "repository_count": len(repositories),
                    "session_id": session_id,
                    "processing_time_ms": int((time.time() - start_time) * 1000),
                },
            )

            return {"repositories": repositories}
        except Exception as e:
            # Enhanced error tracking with comprehensive context
            add_enhanced_error_attributes(
                span,
                e,
                operation="list_repos",
                session_id=session_id,
                tool_name="list_opentelemetry_repos",
                processing_time_ms=int((time.time() - start_time) * 1000),
                repositories_count=(
                    len(repositories) if "repositories" in locals() else 0
                ),
                data_source="opentelemetry_repos.py",
            )

            # Add error event
            span.add_event(
                "tool_execution_failed",
                create_span_event(
                    "tool_execution_failed",
                    "tool",
                    tool_name="list_opentelemetry_repos",
                    error_type=e.__class__.__name__,
                    error_message=str(e),
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    operation_stage="repository_fetch",
                ),
            )

            logger.error(
                "Failed to fetch OpenTelemetry repositories",
                exc_info=True,
                extra={
                    "error_type": e.__class__.__name__,
                    "session_id": session_id,
                    "processing_time_ms": int((time.time() - start_time) * 1000),
                    "tool_name": "list_opentelemetry_repos",
                },
            )
            raise


@app.get("/repos")
async def list_opentelemetry_repos_http():
    """HTTP endpoint for listing OpenTelemetry repositories"""
    result = await list_opentelemetry_repos()
    return result


@mcp.tool
async def list_opentelemetry_issues(repo: str = "opentelemetry-python"):
    """Get OpenTelemetry repository issues

    Returns issues from a specific OpenTelemetry repository

    Args:
        repo: Repository name (e.g. opentelemetry-python)
    """
    session_id = extract_session_id_from_request()
    with create_root_span_context(
        tracer, "mcp.tool.list_opentelemetry_issues", "tool", session_id
    ) as span:
        try:
            add_span_attributes(
                span,
                **{
                    MCPAttributes.MCP_TOOL_NAME: "list_opentelemetry_issues",
                    MCPAttributes.MCP_TOOL_ARGUMENTS: f"repo={repo}",
                    SpanAttributes.CODE_FUNCTION: "list_opentelemetry_issues",
                    "github.repository": repo,
                },
            )

            logger.info("Fetching repository issues", extra={"repository": repo})

            issues = await get_repo_issues(repo)

            add_span_attributes(span, **{"issues.count": len(issues)})

            span.add_event("issues_fetched", {"repository": repo, "count": len(issues)})

            logger.info(
                "Successfully fetched issues",
                extra={"repository": repo, "issue_count": len(issues)},
            )

            return {"issues": issues}
        except Exception as e:
            set_span_error(span, e)
            logger.error(
                "Failed to fetch repository issues",
                exc_info=True,
                extra={"repository": repo},
            )
            raise


@app.get("/issues")
async def list_opentelemetry_issues_http(repo: str = "opentelemetry-python"):
    """HTTP endpoint for getting OpenTelemetry repository issues"""
    result = await list_opentelemetry_issues(repo)
    return result


@mcp.tool
async def search_opentelemetry_issues(
    repo: str = "opentelemetry-python", keywords: str = "metrics"
):
    """Search OpenTelemetry repository issues

    Search for issues in a specific OpenTelemetry repository using keywords

    Args:
        repo: Repository name (e.g. opentelemetry-python)
        keywords: Keywords to search for in issues
    """
    import time

    start_time = time.time()

    session_id = extract_session_id_from_request()
    with create_root_span_context(
        tracer, "mcp.tool.search_opentelemetry_issues", "tool", session_id
    ) as span:
        try:
            # Add comprehensive MCP operation context
            input_data = {"repo": repo, "keywords": keywords}
            add_mcp_operation_context(
                span,
                operation_type="tool",
                operation_name="search_opentelemetry_issues",
                input_data=input_data,
                tool_category="issue_management",
                data_source="github_api",
                search_complexity="keyword_based",
            )

            # Add tool-specific attributes
            add_span_attributes(
                span,
                **{
                    SpanAttributes.CODE_FUNCTION: "search_opentelemetry_issues",
                    MCPAttributes.MCP_TOOL_CATEGORY: "issue_management",
                    "github.repository": repo,
                    "search.keywords": keywords,
                    "search.type": "keyword_based",
                    "api.provider": "github",
                },
            )

            # Add structured span event for search start
            span.add_event(
                "search_started",
                create_span_event(
                    "search_started",
                    "tool",
                    tool_name="search_opentelemetry_issues",
                    repository=repo,
                    keywords=keywords,
                    search_type="github_issues",
                    expected_complexity="medium",
                ),
            )

            logger.info(
                "Searching repository issues",
                extra={
                    "repository": repo,
                    "keywords": keywords,
                    "session_id": session_id,
                    "search_type": "keyword_based",
                },
            )

            issues = await search_repo_issues(repo, keywords)

            # Add operation metrics with search-specific data
            output_data = {"issues": issues}
            add_operation_metrics(
                span,
                operation_type="tool",
                start_time=start_time,
                output_data=output_data,
                search_results_count=len(issues),
                keywords_count=len(keywords.split()),
                api_calls_made=1,
                result_relevance="high" if len(issues) > 0 else "none",
            )

            # Add comprehensive search result attributes
            add_span_attributes(
                span,
                **{
                    "search.results.count": len(issues),
                    "search.keywords.count": len(keywords.split()),
                    "search.success": True,
                    "search.relevance": "high" if len(issues) > 0 else "none",
                    "api.response.success": True,
                },
            )

            # Add detailed search completion event
            span.add_event(
                "issues_searched",
                create_span_event(
                    "issues_searched",
                    "tool",
                    tool_name="search_opentelemetry_issues",
                    repository=repo,
                    keywords=keywords,
                    results_count=len(issues),
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    search_success=True,
                    api_provider="github",
                ),
            )

            logger.info(
                "Successfully searched issues",
                extra={
                    "repository": repo,
                    "keywords": keywords,
                    "results_count": len(issues),
                    "session_id": session_id,
                    "processing_time_ms": int((time.time() - start_time) * 1000),
                },
            )

            return {"issues": issues}
        except Exception as e:
            # Enhanced error tracking with search context
            add_enhanced_error_attributes(
                span,
                e,
                operation="search_issues",
                repository=repo,
                keywords=keywords,
                session_id=session_id,
                tool_name="search_opentelemetry_issues",
                processing_time_ms=int((time.time() - start_time) * 1000),
                search_type="keyword_based",
            )

            # Add error event
            span.add_event(
                "search_failed",
                create_span_event(
                    "search_failed",
                    "tool",
                    tool_name="search_opentelemetry_issues",
                    repository=repo,
                    keywords=keywords,
                    error_type=e.__class__.__name__,
                    error_message=str(e),
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    operation_stage="github_api_search",
                ),
            )

            logger.error(
                "Failed to search repository issues",
                exc_info=True,
                extra={
                    "repository": repo,
                    "keywords": keywords,
                    "error_type": e.__class__.__name__,
                    "session_id": session_id,
                    "processing_time_ms": int((time.time() - start_time) * 1000),
                },
            )
            raise


@app.get("/issues/search")
async def search_opentelemetry_issues_http(
    repo: str = "opentelemetry-python", keywords: str = "metrics"
):
    """HTTP endpoint for searching OpenTelemetry repository issues"""
    result = await search_opentelemetry_issues(repo, keywords)
    return result


@mcp.tool
async def get_opentelemetry_examples():
    """Get OpenTelemetry examples

    Returns a list of OpenTelemetry demo services and examples
    """
    session_id = extract_session_id_from_request()
    with create_root_span_context(
        tracer, "mcp.tool.get_opentelemetry_examples", "tool", session_id
    ) as span:
        try:
            add_span_attributes(
                span,
                **{
                    MCPAttributes.MCP_TOOL_NAME: "get_opentelemetry_examples",
                    MCPAttributes.MCP_TOOL_ARGUMENTS: "none",
                    SpanAttributes.CODE_FUNCTION: "get_opentelemetry_examples",
                },
            )

            logger.info("Fetching OpenTelemetry examples")

            examples = get_demo_services_doc()

            span.add_event(
                "examples_fetched",
                {
                    "has_content": "content" in examples,
                    "has_error": "error" in examples,
                },
            )

            logger.info(
                "Successfully fetched examples",
                extra={
                    "has_content": "content" in examples,
                    "has_error": "error" in examples,
                },
            )

            return {"examples": examples}
        except Exception as e:
            set_span_error(span, e)
            logger.error("Failed to fetch OpenTelemetry examples", exc_info=True)
            raise


@app.get("/examples")
async def get_opentelemetry_examples_http():
    """HTTP endpoint for getting OpenTelemetry examples"""
    result = await get_opentelemetry_examples()
    return result


@mcp.tool
async def get_opentelemetry_examples_by_language(language: str = "python"):
    """Get OpenTelemetry examples by language

    Returns OpenTelemetry examples for a specific programming language

    Args:
        language: Programming language (e.g. python, java, go)
    """
    session_id = extract_session_id_from_request()
    with create_root_span_context(
        tracer, "mcp.tool.get_opentelemetry_examples_by_language", "tool", session_id
    ) as span:
        try:
            add_span_attributes(
                span,
                **{
                    MCPAttributes.MCP_TOOL_NAME: "get_opentelemetry_examples_by_language",
                    MCPAttributes.MCP_TOOL_ARGUMENTS: f"language={language}",
                    SpanAttributes.CODE_FUNCTION: "get_opentelemetry_examples_by_language",
                    "programming.language": language,
                },
            )

            logger.info("Fetching examples by language", extra={"language": language})

            examples = get_demo_services_by_language(language)

            add_span_attributes(
                span, **{"examples.services.count": len(examples.get("services", []))}
            )

            span.add_event(
                "examples_by_language_fetched",
                {
                    "language": language,
                    "services_count": len(examples.get("services", [])),
                },
            )

            logger.info(
                "Successfully fetched examples by language",
                extra={
                    "language": language,
                    "services_count": len(examples.get("services", [])),
                },
            )

            return {"examples": examples}
        except Exception as e:
            set_span_error(span, e)
            logger.error(
                "Failed to fetch examples by language",
                exc_info=True,
                extra={"language": language},
            )
            raise


@app.get("/demo")
async def get_opentelemetry_examples_by_language_http(language: str = "python"):
    """HTTP endpoint for getting OpenTelemetry examples by language"""
    result = await get_opentelemetry_examples_by_language(language)
    return result


@mcp.tool
async def get_opentelemetry_docs_by_language(
    language: str = "python", version: str = None
):
    """Get OpenTelemetry documentation by language and version

    Returns OpenTelemetry documentation for a specific programming language and version

    Args:
        language: Programming language (e.g. python, java, go)
        version: Version to retrieve (e.g. "v1.2.3", "latest", or None for latest)
    """
    session_id = extract_session_id_from_request()
    with create_root_span_context(
        tracer, "mcp.tool.get_opentelemetry_docs_by_language", "tool", session_id
    ) as span:
        try:
            add_span_attributes(
                span,
                **{
                    MCPAttributes.MCP_TOOL_NAME: "get_opentelemetry_docs_by_language",
                    MCPAttributes.MCP_TOOL_ARGUMENTS: f"language={language}",
                    SpanAttributes.CODE_FUNCTION: "get_opentelemetry_docs_by_language",
                    "programming.language": language,
                },
            )

            logger.info(
                "Fetching documentation by language and version",
                extra={"language": language, "version": version},
            )

            # Use unified function with optional version parameter
            docs = await get_docs_by_language(language, version)

            add_span_attributes(
                span,
                **{"docs.sections.count": len(docs) if isinstance(docs, list) else 1},
            )

            span.add_event(
                "docs_by_language_fetched",
                {
                    "language": language,
                    "sections_count": len(docs) if isinstance(docs, list) else 1,
                },
            )

            logger.info(
                "Successfully fetched documentation by language",
                extra={
                    "language": language,
                    "sections_count": len(docs) if isinstance(docs, list) else 1,
                },
            )

            return {"docs": docs}
        except Exception as e:
            set_span_error(span, e)
            logger.error(
                "Failed to fetch documentation by language",
                exc_info=True,
                extra={"language": language},
            )
            raise


@mcp.tool
async def get_semantic_conventions(category: str = None, count: int = 50):
    """Get OpenTelemetry semantic conventions from the semantic-conventions repository

    Returns semantic conventions from the OpenTelemetry semantic-conventions repository
    as markdown documentation files.

    Args:
        category: Optional category filter (e.g., "http", "database", "messaging")
        count: Maximum number of files to retrieve (default: 50)
    """
    import time

    start_time = time.time()

    # Create true root span for this MCP tool operation with session tracking
    session_id = extract_session_id_from_request()
    with create_root_span_context(
        tracer, "mcp.tool.get_semantic_conventions", "tool", session_id
    ) as span:
        try:
            # Add comprehensive MCP operation context
            input_data = {
                "category": category,
                "count": count,
            }
            add_mcp_operation_context(
                span,
                operation_type="tool",
                operation_name="get_semantic_conventions",
                input_data=input_data,
                tool_category="semantic_conventions",
                data_source="github_api",
                cache_enabled=False,
            )

            # Add tool-specific attributes
            add_span_attributes(
                span,
                **{
                    SpanAttributes.CODE_FUNCTION: "get_semantic_conventions",
                    MCPAttributes.MCP_TOOL_CATEGORY: "semantic_conventions",
                    MCPAttributes.MCP_TOOL_NAME: "get_semantic_conventions",
                    MCPAttributes.MCP_TOOL_ARGUMENTS: f"category={category}, count={count}",
                    "github.repository.owner": "open-telemetry",
                    "github.repository.name": "semantic-conventions",
                    "semantic_conventions.format_type": "markdown",
                    "semantic_conventions.category": category or "all",
                    "semantic_conventions.count": count,
                    "data.source": "semantic_conventions.py",
                    "operation.complexity": "high",
                },
            )

            # Add structured span event for tool start
            span.add_event(
                "tool_execution_started",
                create_span_event(
                    "tool_execution_started",
                    "tool",
                    tool_name="get_semantic_conventions",
                    format_type="markdown",
                    category=category or "all",
                    requested_count=count,
                    repository="open-telemetry/semantic-conventions",
                    operation_complexity="high",
                ),
            )

            logger.info(
                "Fetching semantic conventions",
                extra={
                    "format_type": "markdown",
                    "category": category,
                    "count": count,
                    "session_id": session_id,
                },
            )

            # Call the semantic conventions function
            conventions = await fetch_semantic_conventions(category, count)

            # Add operation metrics
            output_data = {"conventions": conventions}
            add_operation_metrics(
                span,
                operation_type="tool",
                start_time=start_time,
                output_data=output_data,
                files_fetched=len(conventions),
                total_size_bytes=sum(conv.get("size", 0) for conv in conventions),
            )

            add_span_attributes(
                span, **{"semantic_conventions.files.fetched": len(conventions)}
            )

            span.add_event(
                "semantic_conventions_fetched",
                create_span_event(
                    "semantic_conventions_fetched",
                    "tool",
                    tool_name="get_semantic_conventions",
                    format_type="markdown",
                    category=category or "all",
                    files_fetched=len(conventions),
                    total_size_bytes=sum(conv.get("size", 0) for conv in conventions),
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    success=True,
                ),
            )

            logger.info(
                "Successfully fetched semantic conventions",
                extra={
                    "format_type": "markdown",
                    "category": category,
                    "files_fetched": len(conventions),
                    "session_id": session_id,
                },
            )

            return {"conventions": conventions}
        except Exception as e:
            # Enhanced error tracking with operation context
            add_enhanced_error_attributes(
                span,
                e,
                format_type="markdown",
                category=category or "all",
                count=count,
                operation="get_semantic_conventions",
                tool_name="get_semantic_conventions",
                session_id=session_id,
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

            # Add error event
            span.add_event(
                "semantic_conventions_fetch_failed",
                create_span_event(
                    "semantic_conventions_fetch_failed",
                    "tool",
                    tool_name="get_semantic_conventions",
                    error_type=e.__class__.__name__,
                    error_message=str(e),
                    format_type="markdown",
                    category=category or "all",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                ),
            )

            logger.error(
                "Failed to fetch semantic conventions",
                exc_info=True,
                extra={
                    "error_type": e.__class__.__name__,
                    "format_type": "markdown",
                    "category": category,
                    "session_id": session_id,
                },
            )
            raise


@app.get("/otel-docs")
async def get_opentelemetry_docs_by_language_http(
    language: str = "python", version: str = None
):
    """HTTP endpoint for getting OpenTelemetry documentation by language and version"""
    result = await get_opentelemetry_docs_by_language(language, version)
    return result


@app.get("/semantic-conventions")
async def get_semantic_conventions_http(category: str = None, count: int = 50):
    """HTTP endpoint for getting OpenTelemetry semantic conventions"""
    result = await fetch_semantic_conventions(category, count)
    return result


@mcp.tool
async def get_instrumentation_score_spec():
    """Get the Instrumentation Score specification

    Returns the main specification document for the Instrumentation Score standard,
    which provides a standardized metric for assessing OpenTelemetry instrumentation quality.
    """
    import time

    start_time = time.time()

    # Create true root span for this MCP tool operation with session tracking
    session_id = extract_session_id_from_request()
    with create_root_span_context(
        tracer, "mcp.tool.get_instrumentation_score_spec", "tool", session_id
    ) as span:
        try:
            # Add comprehensive MCP operation context
            add_mcp_operation_context(
                span,
                operation_type="tool",
                operation_name="get_instrumentation_score_spec",
                input_data={},
                tool_category="instrumentation_quality",
                data_source="github_raw",
                cache_enabled=False,
            )

            # Add tool-specific attributes
            add_span_attributes(
                span,
                **{
                    SpanAttributes.CODE_FUNCTION: "get_instrumentation_score_spec",
                    MCPAttributes.MCP_TOOL_CATEGORY: "instrumentation_quality",
                    MCPAttributes.MCP_TOOL_NAME: "get_instrumentation_score_spec",
                    "github.repository.owner": "instrumentation-score",
                    "github.repository.name": "spec",
                    "document.type": "specification",
                    "data.source": "instrumentation_score.py",
                    "operation.complexity": "low",
                },
            )

            # Add structured span event for tool start
            span.add_event(
                "tool_execution_started",
                create_span_event(
                    "tool_execution_started",
                    "tool",
                    tool_name="get_instrumentation_score_spec",
                    document_type="specification",
                    repository="instrumentation-score/spec",
                    operation_complexity="low",
                ),
            )

            logger.info(
                "Fetching instrumentation score specification",
                extra={
                    "session_id": session_id,
                    "operation": "get_spec",
                    "tool_category": "instrumentation_quality",
                },
            )

            specification = fetch_instrumentation_score_specification()

            # Add operation metrics
            output_data = {"specification": specification}
            add_operation_metrics(
                span,
                operation_type="tool",
                start_time=start_time,
                output_data=output_data,
                content_length=len(specification),
                document_type="specification",
            )

            # Add comprehensive result attributes
            add_span_attributes(
                span,
                **{
                    "specification.content_length": len(specification),
                    "result.success": True,
                    "result.type": "specification_document",
                    "document.format": "markdown",
                    "performance.category": (
                        "fast" if (time.time() - start_time) < 1.0 else "normal"
                    ),
                },
            )

            # Add detailed completion event
            span.add_event(
                "specification_fetched",
                create_span_event(
                    "specification_fetched",
                    "tool",
                    tool_name="get_instrumentation_score_spec",
                    content_length=len(specification),
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    success=True,
                    document_format="markdown",
                ),
            )

            logger.info(
                "Successfully fetched instrumentation score specification",
                extra={
                    "content_length": len(specification),
                    "session_id": session_id,
                    "processing_time_ms": int((time.time() - start_time) * 1000),
                },
            )

            return {"specification": specification}
        except Exception as e:
            # Enhanced error tracking with comprehensive context
            add_enhanced_error_attributes(
                span,
                e,
                operation="get_instrumentation_score_spec",
                session_id=session_id,
                tool_name="get_instrumentation_score_spec",
                processing_time_ms=int((time.time() - start_time) * 1000),
                document_type="specification",
                data_source="github_raw",
            )

            # Add error event
            span.add_event(
                "tool_execution_failed",
                create_span_event(
                    "tool_execution_failed",
                    "tool",
                    tool_name="get_instrumentation_score_spec",
                    error_type=e.__class__.__name__,
                    error_message=str(e),
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    operation_stage="specification_fetch",
                ),
            )

            logger.error(
                "Failed to fetch instrumentation score specification",
                exc_info=True,
                extra={
                    "error_type": e.__class__.__name__,
                    "session_id": session_id,
                    "processing_time_ms": int((time.time() - start_time) * 1000),
                    "tool_name": "get_instrumentation_score_spec",
                },
            )
            raise


@mcp.tool
async def get_instrumentation_score_rules(
    rule_ids: str = None, impact_levels: str = None, targets: str = None
):
    """Get Instrumentation Score rules

    Returns scoring rules from the Instrumentation Score specification.
    Rules can be filtered by ID, impact level, or target type.

    Args:
        rule_ids: Comma-separated list of rule IDs to fetch (e.g., "RES-001,SPA-001")
        impact_levels: Comma-separated list of impact levels (e.g., "Critical,Important")
        targets: Comma-separated list of targets (e.g., "Resource,Span")
    """
    import time

    start_time = time.time()

    # Parse comma-separated parameters
    rule_ids_list = rule_ids.split(",") if rule_ids else None
    impact_levels_list = impact_levels.split(",") if impact_levels else None
    targets_list = targets.split(",") if targets else None

    # Create true root span for this MCP tool operation with session tracking
    session_id = extract_session_id_from_request()
    with create_root_span_context(
        tracer, "mcp.tool.get_instrumentation_score_rules", "tool", session_id
    ) as span:
        try:
            # Add comprehensive MCP operation context
            input_data = {
                "rule_ids": rule_ids_list,
                "impact_levels": impact_levels_list,
                "targets": targets_list,
            }
            add_mcp_operation_context(
                span,
                operation_type="tool",
                operation_name="get_instrumentation_score_rules",
                input_data=input_data,
                tool_category="instrumentation_quality",
                data_source="github_api",
                cache_enabled=False,
            )

            # Add tool-specific attributes
            add_span_attributes(
                span,
                **{
                    SpanAttributes.CODE_FUNCTION: "get_instrumentation_score_rules",
                    MCPAttributes.MCP_TOOL_CATEGORY: "instrumentation_quality",
                    MCPAttributes.MCP_TOOL_NAME: "get_instrumentation_score_rules",
                    MCPAttributes.MCP_TOOL_ARGUMENTS: f"rule_ids={rule_ids}, impact_levels={impact_levels}, targets={targets}",
                    "github.repository.owner": "instrumentation-score",
                    "github.repository.name": "spec",
                    "rules.filter.rule_ids": rule_ids or "all",
                    "rules.filter.impact_levels": impact_levels or "all",
                    "rules.filter.targets": targets or "all",
                    "data.source": "instrumentation_score.py",
                    "operation.complexity": "medium",
                },
            )

            # Add structured span event for tool start
            span.add_event(
                "tool_execution_started",
                create_span_event(
                    "tool_execution_started",
                    "tool",
                    tool_name="get_instrumentation_score_rules",
                    rule_ids_filter=rule_ids or "all",
                    impact_levels_filter=impact_levels or "all",
                    targets_filter=targets or "all",
                    repository="instrumentation-score/spec",
                    operation_complexity="medium",
                ),
            )

            logger.info(
                "Fetching instrumentation score rules",
                extra={
                    "rule_ids": rule_ids,
                    "impact_levels": impact_levels,
                    "targets": targets,
                    "session_id": session_id,
                    "operation": "get_rules",
                    "tool_category": "instrumentation_quality",
                },
            )

            rules_data = fetch_instrumentation_score_rules(
                rule_ids=rule_ids_list,
                impact_levels=impact_levels_list,
                targets=targets_list,
            )

            # Add operation metrics
            output_data = {"rules_data": rules_data}
            add_operation_metrics(
                span,
                operation_type="tool",
                start_time=start_time,
                output_data=output_data,
                rules_fetched=rules_data["metadata"]["fetched"],
                rules_filtered=rules_data["metadata"]["filtered_out"],
                total_available=rules_data["metadata"]["total_available"],
            )

            # Add comprehensive result attributes
            add_span_attributes(
                span,
                **{
                    "rules.fetched": rules_data["metadata"]["fetched"],
                    "rules.filtered_out": rules_data["metadata"]["filtered_out"],
                    "rules.total_available": rules_data["metadata"]["total_available"],
                    "result.success": True,
                    "result.type": "rules_collection",
                    "performance.category": (
                        "fast" if (time.time() - start_time) < 2.0 else "normal"
                    ),
                },
            )

            # Add detailed completion event
            span.add_event(
                "rules_fetched",
                create_span_event(
                    "rules_fetched",
                    "tool",
                    tool_name="get_instrumentation_score_rules",
                    rules_fetched=rules_data["metadata"]["fetched"],
                    rules_filtered=rules_data["metadata"]["filtered_out"],
                    total_available=rules_data["metadata"]["total_available"],
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    success=True,
                ),
            )

            logger.info(
                "Successfully fetched instrumentation score rules",
                extra={
                    "rules_fetched": rules_data["metadata"]["fetched"],
                    "rules_filtered": rules_data["metadata"]["filtered_out"],
                    "total_available": rules_data["metadata"]["total_available"],
                    "session_id": session_id,
                    "processing_time_ms": int((time.time() - start_time) * 1000),
                },
            )

            return rules_data
        except Exception as e:
            # Enhanced error tracking with comprehensive context
            add_enhanced_error_attributes(
                span,
                e,
                operation="get_instrumentation_score_rules",
                rule_ids=rule_ids or "all",
                impact_levels=impact_levels or "all",
                targets=targets or "all",
                session_id=session_id,
                tool_name="get_instrumentation_score_rules",
                processing_time_ms=int((time.time() - start_time) * 1000),
                data_source="github_api",
            )

            # Add error event
            span.add_event(
                "tool_execution_failed",
                create_span_event(
                    "tool_execution_failed",
                    "tool",
                    tool_name="get_instrumentation_score_rules",
                    error_type=e.__class__.__name__,
                    error_message=str(e),
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    operation_stage="rules_fetch",
                ),
            )

            logger.error(
                "Failed to fetch instrumentation score rules",
                exc_info=True,
                extra={
                    "error_type": e.__class__.__name__,
                    "rule_ids": rule_ids,
                    "impact_levels": impact_levels,
                    "targets": targets,
                    "session_id": session_id,
                    "processing_time_ms": int((time.time() - start_time) * 1000),
                    "tool_name": "get_instrumentation_score_rules",
                },
            )
            raise


# Add health check endpoint for Kubernetes
@app.get("/health")
async def health_check():
    """Health check endpoint for Kubernetes probes.

    Returns comprehensive health status including:
    - Service status
    - MCP server availability
    - Environment configuration
    """
    try:
        # Basic health check - if we can respond, the service is running
        health_status = {
            "status": "healthy",
            "service": "otel-instrumentation-mcp-server",
            "timestamp": asyncio.get_event_loop().time(),
            "transport": os.getenv("MCP_TRANSPORT", "stdio"),
            "port": os.getenv("SERVICE_PORT") or os.getenv("MCP_PORT", "8080"),
            "mcp_available": True,
        }

        return health_status
    except Exception as e:
        # Only log errors for health checks, not successful ones
        logger.error("Health check failed", exc_info=True)

        # Return unhealthy status if any critical component fails
        return {
            "status": "unhealthy",
            "service": "otel-instrumentation-mcp-server",
            "error": str(e),
            "timestamp": asyncio.get_event_loop().time(),
        }


# Add readiness check endpoint for more specific readiness validation
@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint for Kubernetes readiness probes.

    This endpoint performs more thorough checks to determine if the service
    is ready to accept traffic, including MCP server initialization status.
    """
    try:
        # Check if MCP server is properly initialized
        mcp_ready = mcp is not None

        # Check if FastAPI app is properly configured
        app_ready = app is not None and len(app.routes) > 0

        # All systems ready
        if mcp_ready and app_ready:
            return {
                "status": "ready",
                "service": "otel-instrumentation-mcp-server",
                "mcp_initialized": mcp_ready,
                "app_initialized": app_ready,
                "timestamp": asyncio.get_event_loop().time(),
            }
        else:
            # Only log when not ready (which is unusual and worth noting)
            logger.warning(
                "Service not ready",
                extra={"mcp_initialized": mcp_ready, "app_initialized": app_ready},
            )
            return {
                "status": "not_ready",
                "service": "otel-instrumentation-mcp-server",
                "mcp_initialized": mcp_ready,
                "app_initialized": app_ready,
                "timestamp": asyncio.get_event_loop().time(),
            }
    except Exception as e:
        # Only log errors for readiness checks
        logger.error("Readiness check failed", exc_info=True)
        return {
            "status": "not_ready",
            "service": "otel-instrumentation-mcp-server",
            "error": str(e),
            "timestamp": asyncio.get_event_loop().time(),
        }


# Add root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "OpenTelemetry Instrumentation MCP Server",
        "mcp_http_endpoint": "/mcp/",
        "mcp_sse_endpoint": "/sse/",
        "health_endpoint": "/health",
    }


# Mount the MCP servers at different paths for proper MCP protocol support
app.mount("/mcp", mcp_http_app)  # HTTP streaming transport
app.mount("/sse", mcp_sse_app)  # SSE transport


def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown."""

    def signal_handler(signum, frame):
        signal_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        print(f"\nReceived {signal_name}. Shutting down gracefully...")
        sys.exit(0)

    # Handle SIGTERM (Kubernetes sends this for graceful shutdown)
    signal.signal(signal.SIGTERM, signal_handler)
    # Handle SIGINT (Ctrl+C) - but let uvicorn handle it for HTTP servers
    if (
        os.getenv("SERVICE_PORT") is None
        and os.getenv("MCP_TRANSPORT", "stdio").lower() == "stdio"
    ):
        signal.signal(signal.SIGINT, signal_handler)


def main():
    """Main entry point for the MCP server."""
    with tracer.start_as_current_span("mcp.server.main") as span:
        try:
            add_span_attributes(
                span,
                **{
                    SpanAttributes.CODE_FUNCTION: "main",
                },
            )

            # Set up signal handlers for graceful shutdown
            setup_signal_handlers()

            # Check for transport configuration
            transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
            service_port = os.getenv("SERVICE_PORT")
            mcp_port = os.getenv("MCP_PORT", "8080")

            add_span_attributes(
                span,
                **{
                    MCPAttributes.MCP_TRANSPORT: transport,
                    "server.port": service_port or mcp_port,
                },
            )

            # Automatically detect optimal host binding
            host = get_optimal_host_binding()

            # Validate the host binding before starting
            if not validate_host_binding(host):
                logger.warning(
                    f"Host binding {host} validation failed, falling back to 0.0.0.0"
                )
                host = "0.0.0.0"

            span.add_event(
                "server_starting",
                {
                    "transport": transport,
                    "host": host,
                    "port": service_port or mcp_port,
                },
            )

            # If SERVICE_PORT is set, use HTTP transport with both HTTP and SSE endpoints
            if service_port:
                port = int(service_port)
                logger.info(
                    f"Starting MCP server with HTTP transport (both /mcp and /sse endpoints) on {host}:{port}"
                )
                try:
                    # Use uvicorn to run the FastAPI app with both transports
                    uvicorn.run(app, host=host, port=port, log_level="info")
                except KeyboardInterrupt:
                    logger.info("Shutting down gracefully...")
            elif transport == "sse":
                port = int(mcp_port)
                logger.info(f"Starting MCP server with SSE transport on {host}:{port}")
                try:
                    mcp.run(
                        transport="sse",
                        host=host,
                        port=port,
                    )
                except KeyboardInterrupt:
                    logger.info("Shutting down gracefully...")
            elif transport == "http":
                port = int(mcp_port)
                logger.info(
                    f"Starting MCP server with HTTP transport (both /mcp and /sse endpoints) on {host}:{port}"
                )
                try:
                    # Use uvicorn to run the FastAPI app with both transports
                    uvicorn.run(app, host=host, port=port, log_level="info")
                except KeyboardInterrupt:
                    logger.info("Shutting down gracefully...")
            else:
                # Default to stdio transport
                logger.info("Starting MCP server with STDIO transport")
                try:
                    mcp.run()
                except KeyboardInterrupt:
                    logger.info("Shutting down gracefully...")
                    sys.exit(0)
        except Exception as e:
            set_span_error(span, e)
            logger.error("Failed to start MCP server", exc_info=True)
            raise


if __name__ == "__main__":
    main()
