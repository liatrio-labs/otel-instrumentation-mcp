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

"""
OpenTelemetry Semantic Conventions module for MCP Server.

This module provides functionality to fetch semantic conventions from the
OpenTelemetry semantic-conventions repository, including both markdown documentation
and YAML model files.
"""

import os
import asyncio
import requests
from typing import List, Dict, Any, Optional
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Status, StatusCode

from .telemetry import (
    get_tracer,
    get_logger,
    set_span_error,
    add_span_attributes,
    add_enhanced_error_attributes,
    create_span_event,
)
from .github_app_auth import github_app_auth, GitHubAppAuthError

GITHUB_API_URL = os.getenv("GITHUB_GRAPHQL_URL", "https://api.github.com/graphql")

tracer = get_tracer()
logger = get_logger()


async def get_semantic_conventions(
    category: Optional[str] = None, count: int = 50
) -> List[Dict[str, Any]]:
    """
    Get OpenTelemetry semantic conventions from the semantic-conventions repository.

    Args:
        category: Optional category filter (e.g., "http", "database", "messaging")
        count: Maximum number of files to retrieve (default: 50)

    Returns:
        List of semantic convention markdown files with their content and metadata
    """
    with tracer.start_as_current_span("github.get_semantic_conventions") as span:
        try:
            # Add comprehensive attributes with enhanced context
            add_span_attributes(
                span,
                **{
                    SpanAttributes.CODE_FUNCTION: "get_semantic_conventions",
                    "github.repository.owner": "open-telemetry",
                    "github.repository.name": "semantic-conventions",
                    "github.query.format_type": "markdown",
                    "github.query.category": category or "all",
                    "github.query.count": count,
                    "github.api.type": "graphql",
                    "operation.type": "data_fetch",
                    "data.source": "github_api",
                },
            )

            # Add operation start event
            span.add_event(
                "semantic_conventions_request_started",
                create_span_event(
                    "semantic_conventions_request_started",
                    "data_fetch",
                    repository="open-telemetry/semantic-conventions",
                    format_type="markdown",
                    category=category or "all",
                    requested_count=count,
                    api_type="graphql",
                    operation="get_semantic_conventions",
                ),
            )

            # Get authentication headers (GitHub App or fallback to personal token)
            # Authentication is optional - GitHub API works without auth but with rate limits
            headers = {"Accept": "application/vnd.github+json"}
            try:
                auth_headers = await github_app_auth.get_auth_headers()
                headers.update(auth_headers)

                # Add auth info to span
                auth_info = github_app_auth.get_auth_info()
                add_span_attributes(
                    span,
                    **{
                        "github.auth.type": auth_info["auth_type"],
                        "github.auth.configured": auth_info["configured"],
                    },
                )

                span.add_event(
                    "github_auth_obtained",
                    create_span_event(
                        "github_auth_obtained",
                        "authentication",
                        auth_type=auth_info["auth_type"],
                        configured=auth_info["configured"],
                    ),
                )

            except GitHubAppAuthError:
                span.add_event(
                    "using_unauthenticated_request",
                    create_span_event(
                        "using_unauthenticated_request",
                        "authentication",
                        reason="no_github_auth",
                        rate_limit_applies=True,
                    ),
                )
                logger.info(
                    "No GitHub authentication available, using unauthenticated request"
                )

            # Build the GraphQL query for markdown files only
            query = """
            query {
                repository(owner: "open-telemetry", name: "semantic-conventions") {
                    docs: object(expression: "HEAD:docs") {
                        ... on Tree {
                            entries {
                                name
                                path
                                type
                                object {
                                    ... on Tree {
                                        entries {
                                            name
                                            path
                                            type
                                            object {
                                                ... on Blob {
                                                    text
                                                    byteSize
                                                }
                                            }
                                        }
                                    }
                                    ... on Blob {
                                        text
                                        byteSize
                                    }
                                }
                            }
                        }
                    }
                }
            }
            """

            # Add HTTP semantic conventions for the GraphQL request
            add_span_attributes(
                span,
                **{
                    SpanAttributes.HTTP_METHOD: "POST",
                    SpanAttributes.HTTP_URL: GITHUB_API_URL,
                    SpanAttributes.HTTP_REQUEST_CONTENT_LENGTH: len(query),
                    SpanAttributes.USER_AGENT_ORIGINAL: "otel-instrumentation-mcp-server/0.10.0",
                },
            )

            logger.info(
                "Making GitHub GraphQL request for semantic conventions",
                extra={
                    "repository": "open-telemetry/semantic-conventions",
                    "format_type": "markdown",
                    "category": category,
                    "count": count,
                },
            )

            response = requests.post(
                GITHUB_API_URL, headers=headers, json={"query": query}
            )

            add_span_attributes(
                span,
                **{
                    SpanAttributes.HTTP_STATUS_CODE: response.status_code,
                    SpanAttributes.HTTP_RESPONSE_CONTENT_LENGTH: len(response.content),
                },
            )

            # Check for rate limiting before raising for status
            if response.status_code in (403, 429):
                from .telemetry import handle_rate_limit_error

                error_info = handle_rate_limit_error(
                    span,
                    response,
                    "fetch_semantic_conventions",
                    format_type="markdown",
                    category=category or "all",
                    count=count,
                )

                logger.warning(
                    "Rate limited while fetching semantic conventions",
                    extra={
                        "format_type": "markdown",
                        "category": category or "all",
                        "status_code": response.status_code,
                        "retry_after_seconds": error_info.get("retry_after_seconds"),
                        "rate_limit_info": error_info.get("rate_limit_info"),
                    },
                )

                # Return empty list gracefully instead of raising
                return []

            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                raise Exception(f"GraphQL errors: {data['errors']}")

            # Process the response and extract markdown files
            files = []
            repo_data = data["data"]["repository"]

            # Process docs (markdown files only)
            if "docs" in repo_data and repo_data["docs"]:
                files.extend(_process_docs_tree(repo_data["docs"], category))

            # Limit results to requested count
            files = files[:count]

            add_span_attributes(
                span, **{"semantic_conventions.files.count": len(files)}
            )

            span.add_event(
                "semantic_conventions_fetched",
                {
                    "repository": "open-telemetry/semantic-conventions",
                    "format_type": "markdown",
                    "category": category or "all",
                    "files_count": len(files),
                    "status_code": response.status_code,
                },
            )

            logger.info(
                "Successfully fetched semantic conventions",
                extra={
                    "repository": "open-telemetry/semantic-conventions",
                    "format_type": "markdown",
                    "category": category,
                    "files_count": len(files),
                },
            )

            return files

        except Exception as e:
            set_span_error(span, e)
            logger.error(
                "Failed to fetch semantic conventions",
                exc_info=True,
                extra={
                    "repository": "open-telemetry/semantic-conventions",
                    "format_type": "markdown",
                    "category": category,
                },
            )
            raise


def _process_docs_tree(
    docs_tree: Dict[str, Any], category_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Process the docs tree from GraphQL response to extract markdown files."""
    files = []

    if not docs_tree or "entries" not in docs_tree:
        return files

    for entry in docs_tree["entries"]:
        if entry["type"] == "tree":
            # This is a category directory (e.g., http, database, etc.)
            category_name = entry["name"]

            # Skip if category filter is specified and doesn't match
            if category_filter and category_filter.lower() != category_name.lower():
                continue

            if entry["object"] and "entries" in entry["object"]:
                for file_entry in entry["object"]["entries"]:
                    if (
                        file_entry["type"] == "blob"
                        and file_entry["name"].endswith(".md")
                        and file_entry["object"]
                    ):

                        files.append(
                            {
                                "name": file_entry["name"],
                                "path": file_entry["path"],
                                "type": "markdown",
                                "category": category_name,
                                "content": file_entry["object"]["text"],
                                "size": file_entry["object"]["byteSize"],
                                "url": f"https://github.com/open-telemetry/semantic-conventions/blob/main/{file_entry['path']}",
                            }
                        )
        elif entry["type"] == "blob" and entry["name"].endswith(".md"):
            # Root level markdown file
            if entry["object"]:
                files.append(
                    {
                        "name": entry["name"],
                        "path": entry["path"],
                        "type": "markdown",
                        "category": "general",
                        "content": entry["object"]["text"],
                        "size": entry["object"]["byteSize"],
                        "url": f"https://github.com/open-telemetry/semantic-conventions/blob/main/{entry['path']}",
                    }
                )

    return files
