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

import os
import asyncio
import requests
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


async def get_repo_issues(repo: str, owner: str = "open-telemetry", count: int = 10):
    import time

    start_time = time.time()

    with tracer.start_as_current_span("github.get_repo_issues") as span:
        try:
            # Add comprehensive attributes with enhanced context
            add_span_attributes(
                span,
                **{
                    SpanAttributes.CODE_FUNCTION: "get_repo_issues",
                    "github.repository.owner": owner,
                    "github.repository.name": repo,
                    "github.query.count": count,
                    "github.api.type": "graphql",
                    "operation.type": "data_fetch",
                    "data.source": "github_api",
                },
            )

            # Add operation start event
            span.add_event(
                "github_api_request_started",
                create_span_event(
                    "github_api_request_started",
                    "data_fetch",
                    repository=f"{owner}/{repo}",
                    requested_count=count,
                    api_type="graphql",
                    operation="get_issues",
                ),
            )

            if owner != "open-telemetry":
                span.add_event(
                    "invalid_owner_rejected",
                    create_span_event(
                        "invalid_owner_rejected",
                        "validation",
                        owner=owner,
                        expected_owner="open-telemetry",
                        action="return_empty_result",
                    ),
                )
                logger.warning("Invalid repository owner", extra={"owner": owner})
                return []  # Return empty result if not in open-telemetry org

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

            query = f"""
            query {{
              repository(owner: "{owner}", name: "{repo}") {{
                  issues(first: {count}, orderBy: {{field: CREATED_AT, direction: DESC}}) {{
                    nodes {{
                      title
                      url
                      state
                      createdAt
                      labels(first: 5) {{
                        nodes {{
                          name
                        }}
                      }}
                    }}
                  }}
                }}
              }}
            """

            # Add HTTP semantic conventions for the GraphQL request
            add_span_attributes(
                span,
                **{
                    SpanAttributes.HTTP_METHOD: "POST",
                    SpanAttributes.HTTP_URL: GITHUB_API_URL,
                    SpanAttributes.HTTP_REQUEST_CONTENT_LENGTH: len(query),
                    SpanAttributes.USER_AGENT_ORIGINAL: "otel-instrumentation-mcp-server/0.4.1",
                },
            )

            logger.info(
                "Making GitHub GraphQL request",
                extra={"repository": f"{owner}/{repo}", "count": count},
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
                    "fetch_repository_issues",
                    repository=f"{owner}/{repo}",
                    count=count,
                )

                logger.warning(
                    "Rate limited while fetching repository issues",
                    extra={
                        "repository": f"{owner}/{repo}",
                        "status_code": response.status_code,
                        "retry_after_seconds": error_info.get("retry_after_seconds"),
                        "rate_limit_info": error_info.get("rate_limit_info"),
                    },
                )

                # Return empty list gracefully instead of raising
                return []

            response.raise_for_status()
            data = response.json()
            issues = data["data"]["repository"]["issues"]["nodes"]

            add_span_attributes(span, **{"github.issues.count": len(issues)})

            span.add_event(
                "issues_fetched",
                {
                    "repository": f"{owner}/{repo}",
                    "issues_count": len(issues),
                    "status_code": response.status_code,
                },
            )

            logger.info(
                "Successfully fetched repository issues",
                extra={"repository": f"{owner}/{repo}", "issues_count": len(issues)},
            )

            return issues
        except Exception as e:
            set_span_error(span, e)
            logger.error(
                "Failed to fetch repository issues",
                exc_info=True,
                extra={"repository": f"{owner}/{repo}"},
            )
            raise


async def search_repo_issues(
    repo: str, keywords: str, owner: str = "open-telemetry", count: int = 10
):
    with tracer.start_as_current_span("github.search_repo_issues") as span:
        try:
            add_span_attributes(
                span,
                **{
                    SpanAttributes.CODE_FUNCTION: "search_repo_issues",
                    "github.repository.owner": owner,
                    "github.repository.name": repo,
                    "github.search.keywords": keywords,
                    "github.query.count": count,
                },
            )

            if owner != "open-telemetry":
                span.add_event("invalid_owner", {"owner": owner})
                logger.warning("Invalid repository owner", extra={"owner": owner})
                return []  # Return empty result if not in open-telemetry org

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

            except GitHubAppAuthError:
                span.add_event("using_unauthenticated_request")
                logger.info(
                    "No GitHub authentication available, using unauthenticated request"
                )

            search_query = f"repo:{owner}/{repo} is:issue {keywords}"
            query = f"""
            query {{
              search(query: "{search_query}", type: ISSUE, first: {count}) {{
                nodes {{
                  ... on Issue {{
                    title
                    url
                    state
                    createdAt
                    labels(first: 5) {{
                      nodes {{
                        name
                      }}
                    }}
                  }}
                }}
              }}
            }}
            """

            # Add HTTP semantic conventions for the GraphQL request
            add_span_attributes(
                span,
                **{
                    SpanAttributes.HTTP_METHOD: "POST",
                    SpanAttributes.HTTP_URL: GITHUB_API_URL,
                    SpanAttributes.HTTP_REQUEST_CONTENT_LENGTH: len(query),
                    SpanAttributes.USER_AGENT_ORIGINAL: "otel-instrumentation-mcp-server/0.4.1",
                },
            )

            logger.info(
                "Making GitHub GraphQL search request",
                extra={
                    "repository": f"{owner}/{repo}",
                    "keywords": keywords,
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
                    "search_repository_issues",
                    repository=f"{owner}/{repo}",
                    keywords=keywords,
                    count=count,
                )

                logger.warning(
                    "Rate limited while searching repository issues",
                    extra={
                        "repository": f"{owner}/{repo}",
                        "keywords": keywords,
                        "status_code": response.status_code,
                        "retry_after_seconds": error_info.get("retry_after_seconds"),
                        "rate_limit_info": error_info.get("rate_limit_info"),
                    },
                )

                # Return empty list gracefully instead of raising
                return []

            response.raise_for_status()
            data = response.json()
            issues = data["data"]["search"]["nodes"]

            add_span_attributes(span, **{"github.search.results.count": len(issues)})

            span.add_event(
                "issues_searched",
                {
                    "repository": f"{owner}/{repo}",
                    "keywords": keywords,
                    "results_count": len(issues),
                    "status_code": response.status_code,
                },
            )

            logger.info(
                "Successfully searched repository issues",
                extra={
                    "repository": f"{owner}/{repo}",
                    "keywords": keywords,
                    "results_count": len(issues),
                },
            )

            return issues
        except Exception as e:
            set_span_error(span, e)
            logger.error(
                "Failed to search repository issues",
                exc_info=True,
                extra={"repository": f"{owner}/{repo}", "keywords": keywords},
            )
            raise
