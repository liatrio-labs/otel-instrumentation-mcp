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

import requests
import re
from typing import Optional
from markdown import markdown
from bs4 import BeautifulSoup
from opentelemetry.semconv.trace import SpanAttributes

from .telemetry import get_tracer, get_logger, set_span_error, add_span_attributes
from .version_resolver import GitHubVersionResolver
from .repo_configs import get_repo_config
from .cache import cache_manager

tracer = get_tracer()
logger = get_logger()


async def get_docs_by_language(language: str, version: Optional[str] = None):
    """Get OpenTelemetry documentation by language with optional version.

    Args:
        language: Programming language (e.g., "python", "java", "go")
        version: Version to retrieve (e.g., "v1.2.3", "latest", None for main branch)

    Returns:
        Dictionary containing documentation content and metadata
    """
    # Define cache TTL based on version type
    cache_ttl = 86400  # 24 hours for stable versions
    if version is None or version == "main" or version == "latest":
        cache_ttl = 3600  # 1 hour for main/latest

    async def fetch_docs():
        return await _fetch_docs_by_language(language, version)

    # Use cache manager to get or fetch docs
    return await cache_manager.get_or_set(
        operation="docs_by_language",
        fetch_func=fetch_docs,
        ttl=cache_ttl,
        language=language,
        version=version,
    )


async def _fetch_docs_by_language(language: str, version: Optional[str] = None):
    """Internal function to fetch docs without caching."""
    with tracer.start_as_current_span("opentelemetry.get_docs_by_language") as span:
        try:
            # Get repository configuration
            repo_config = get_repo_config("opentelemetry-docs")
            version_resolver = GitHubVersionResolver(repo_config)

            # Resolve version and add VCS attributes
            version_info = await version_resolver.resolve_version(version)
            version_resolver.add_vcs_attributes_to_span(span, version_info)

            # Add function-specific attributes
            add_span_attributes(
                span,
                **{
                    SpanAttributes.CODE_FUNCTION: "get_docs_by_language",
                    "programming.language": language,
                    "version.requested": version or "main",
                    "version.resolved": version_info.resolved_version,
                },
            )

            # Build versioned URL
            language = language.strip().lower()
            path = f"content/en/docs/languages/{language}/getting-started.md"
            raw_url = version_resolver.build_raw_url(
                path, version_info.resolved_version
            )

            add_span_attributes(
                span,
                **{
                    SpanAttributes.HTTP_METHOD: "GET",
                    SpanAttributes.HTTP_URL: raw_url,
                    "http.url.versioned": version is not None,
                },
            )

            logger.info(
                "Fetching OpenTelemetry documentation",
                extra={
                    "language": language,
                    "version": version_info.resolved_version,
                    "url": raw_url,
                },
            )

            response = requests.get(raw_url)

            add_span_attributes(
                span,
                **{
                    SpanAttributes.HTTP_STATUS_CODE: response.status_code,
                    SpanAttributes.HTTP_RESPONSE_CONTENT_LENGTH: len(response.content),
                },
            )

            if response.status_code == 404:
                span.add_event(
                    "docs_not_found",
                    {"language": language, "version": version_info.resolved_version},
                )
                logger.warning(
                    "No documentation found for language and version",
                    extra={
                        "language": language,
                        "version": version_info.resolved_version,
                    },
                )
                return {
                    "language": language,
                    "version": version_info.resolved_version,
                    "message": f"No docs found for language: {language} version: {version_info.resolved_version}",
                }

            response.raise_for_status()

            # Process content
            with tracer.start_as_current_span("markdown.convert_to_html") as md_span:
                html = markdown(response.text)
                add_span_attributes(
                    md_span, **{"markdown.content_length": len(response.text)}
                )

            with tracer.start_as_current_span("html.extract_text") as html_span:
                soup = BeautifulSoup(html, "html.parser")
                plain_text = soup.get_text()
                add_span_attributes(html_span, **{"html.content_length": len(html)})

            with tracer.start_as_current_span("text.clean_and_normalize") as clean_span:
                cleaned_text = re.sub(r"[^\w\s]", "", plain_text)
                cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()

                add_span_attributes(
                    clean_span,
                    **{
                        "text.original_length": len(plain_text),
                        "text.cleaned_length": len(cleaned_text),
                    },
                )

            result = {
                "language": language,
                "version": version_info.resolved_version,
                "version_info": {
                    "resolved_version": version_info.resolved_version,
                    "ref_type": version_info.ref_type,
                    "resolution_source": version_info.resolution_source,
                    "is_semantic": version_info.is_semantic,
                },
                "content": [{"url": raw_url, "cleaned_text": cleaned_text}],
            }

            span.add_event(
                "docs_processed",
                {
                    "language": language,
                    "version": version_info.resolved_version,
                    "content_length": len(cleaned_text),
                    "status_code": response.status_code,
                },
            )

            logger.info(
                "Successfully processed OpenTelemetry documentation",
                extra={
                    "language": language,
                    "version": version_info.resolved_version,
                    "content_length": len(cleaned_text),
                },
            )

            return result

        except Exception as e:
            set_span_error(span, e)
            logger.error(
                "Failed to get documentation by language",
                exc_info=True,
                extra={"language": language, "version": version},
            )
            raise
