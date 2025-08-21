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
import requests
from opentelemetry.semconv.trace import SpanAttributes

from .telemetry import get_tracer, get_logger, set_span_error, add_span_attributes
from .cache import cache_manager

GITHUB_API_URL = os.getenv("GITHUB_GRAPHQL_URL", "https://api.github.com/graphql")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

tracer = get_tracer()
logger = get_logger()


async def get_opentelemetry_repos():
    # Use cache for repository list with 24-hour TTL (stable content)
    return await cache_manager.get_or_set(
        operation="list_repos",
        fetch_func=_fetch_opentelemetry_repos_uncached,
        ttl=24 * 60 * 60,  # 24 hours
    )


async def _fetch_opentelemetry_repos_uncached():
    with tracer.start_as_current_span("github.get_opentelemetry_repos") as span:
        try:
            add_span_attributes(
                span,
                **{
                    SpanAttributes.CODE_FUNCTION: "get_opentelemetry_repos",
                    "github.organization": "open-telemetry",
                },
            )

            if not GITHUB_TOKEN:
                span.add_event("no_github_token")
                logger.info("No GitHub token provided, returning sample data")
                return [
                    {
                        "name": "opentelemetry-python",
                        "description": "OpenTelemetry Python API and SDK",
                        "url": "https://github.com/open-telemetry/opentelemetry-python",
                        "isArchived": False,
                        "stargazerCount": 1500,
                        "updatedAt": "2024-01-01T00:00:00Z",
                    }
                ]

            headers = {
                "Authorization": f"bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
            }

            query = """
            query {
              organization(login: "open-telemetry") {
                repositories(first: 100, orderBy: {field: NAME, direction: ASC}) {
                  nodes {
                    name
                    description
                    url
                    isArchived
                    stargazerCount
                    updatedAt
                  }
                  pageInfo {
                    hasNextPage
                    endCursor
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
                    SpanAttributes.USER_AGENT_ORIGINAL: "otel-instrumentation-mcp-server/0.4.1",
                },
            )

            logger.info("Making GitHub GraphQL request for repositories")

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
                    "fetch_opentelemetry_repositories",
                    organization="open-telemetry",
                )

                logger.warning(
                    "Rate limited while fetching OpenTelemetry repositories",
                    extra={
                        "organization": "open-telemetry",
                        "status_code": response.status_code,
                        "retry_after_seconds": error_info.get("retry_after_seconds"),
                        "rate_limit_info": error_info.get("rate_limit_info"),
                    },
                )

                # Return empty list gracefully instead of raising
                return []

            response.raise_for_status()
            data = response.json()
            repos = data["data"]["organization"]["repositories"]["nodes"]

            # Filter client-side for names starting with "opentelemetry-"
            filtered_repos = [
                {
                    "name": repo["name"],
                    "description": repo["description"],
                    "url": repo["url"],
                    "stars": repo["stargazerCount"],
                    "archived": repo["isArchived"],
                    "updatedAt": repo["updatedAt"],
                }
                for repo in repos
                if repo["name"].startswith("opentelemetry-")
            ]

            add_span_attributes(
                span,
                **{
                    "github.repositories.total": len(repos),
                    "github.repositories.filtered": len(filtered_repos),
                },
            )

            span.add_event(
                "repositories_fetched",
                {
                    "total_repos": len(repos),
                    "filtered_repos": len(filtered_repos),
                    "status_code": response.status_code,
                },
            )

            logger.info(
                "Successfully fetched OpenTelemetry repositories",
                extra={
                    "total_repos": len(repos),
                    "filtered_repos": len(filtered_repos),
                },
            )

            return filtered_repos
        except Exception as e:
            set_span_error(span, e)
            logger.error("Failed to fetch OpenTelemetry repositories", exc_info=True)
            raise
