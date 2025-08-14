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
Instrumentation Score specification and rules fetcher.

This module provides tools to fetch the Instrumentation Score specification
and rules from the instrumentation-score/spec GitHub repository.
"""


import logging
from typing import Dict, List, Optional, Any
import requests
from opentelemetry import trace

from otel_instrumentation_mcp.telemetry import (
    get_tracer,
    create_root_span_context,
    add_enhanced_error_attributes,
    MCPAttributes,
)
from .cache import cache_manager

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

INSTRUMENTATION_SCORE_REPO_BASE = (
    "https://raw.githubusercontent.com/instrumentation-score/spec/main"
)
GITHUB_API_BASE = "https://api.github.com/repos/instrumentation-score/spec"


async def fetch_instrumentation_score_specification() -> str:
    """
    Fetch the main instrumentation score specification document with caching.

    Returns:
        str: The specification content in markdown format
    """
    # Use cache for instrumentation score specification with 24-hour TTL (stable content)
    return await cache_manager.get_or_set(
        operation="get_instrumentation_score_spec",
        fetch_func=_fetch_instrumentation_score_specification_uncached,
        ttl=24 * 60 * 60,  # 24 hours
    )


async def _fetch_instrumentation_score_specification_uncached() -> str:
    """
    Fetch the main instrumentation score specification document (uncached).

    Returns:
        str: The specification content in markdown format

    Raises:
        Exception: If the specification cannot be fetched
    """
    tracer = get_tracer()

    with create_root_span_context(
        tracer, "fetch_instrumentation_score_specification", "tool"
    ) as span:
        try:
            url = f"{INSTRUMENTATION_SCORE_REPO_BASE}/specification.md"
            span.set_attribute("http.url", url)
            span.set_attribute(
                MCPAttributes.MCP_TOOL_NAME, "get_instrumentation_score_spec"
            )

            response = requests.get(url, timeout=30)
            span.set_attribute("http.status_code", response.status_code)

            if response.status_code == 200:
                content = response.text
                span.set_attribute("content.length", len(content))
                logger.info("Successfully fetched instrumentation score specification")
                return content
            else:
                error_msg = (
                    f"Failed to fetch specification: HTTP {response.status_code}"
                )
                span.record_exception(Exception(error_msg))
                raise Exception(error_msg)

        except Exception as e:
            add_enhanced_error_attributes(span, e, fetch_specification_error="true")
            logger.error(f"Error fetching instrumentation score specification: {e}")
            raise


async def fetch_instrumentation_score_rules(
    rule_ids: Optional[List[str]] = None,
    impact_levels: Optional[List[str]] = None,
    targets: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Fetch instrumentation score rules from the GitHub repository with caching.

    Args:
        rule_ids: Optional list of specific rule IDs to fetch (e.g., ["RES-001", "SPA-001"])
        impact_levels: Optional list of impact levels to filter by (e.g., ["Critical", "Important"])
        targets: Optional list of targets to filter by (e.g., ["Resource", "Span"])

    Returns:
        Dict containing rules information with metadata
    """
    # Use cache for instrumentation score rules with 6-hour TTL
    return await cache_manager.get_or_set(
        operation="get_instrumentation_score_rules",
        fetch_func=lambda: _fetch_instrumentation_score_rules_uncached(
            rule_ids, impact_levels, targets
        ),
        ttl=6 * 60 * 60,  # 6 hours
        rule_ids=rule_ids,
        impact_levels=impact_levels,
        targets=targets,
    )


async def _fetch_instrumentation_score_rules_uncached(
    rule_ids: Optional[List[str]] = None,
    impact_levels: Optional[List[str]] = None,
    targets: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Fetch instrumentation score rules from the GitHub repository (uncached).

    Args:
        rule_ids: Optional list of specific rule IDs to fetch (e.g., ["RES-001", "SPA-001"])
        impact_levels: Optional list of impact levels to filter by (e.g., ["Critical", "Important"])
        targets: Optional list of targets to filter by (e.g., ["Resource", "Span"])

    Returns:
        Dict containing rules information with metadata

    Raises:
        Exception: If rules cannot be fetched
    """
    tracer = get_tracer()

    with create_root_span_context(
        tracer, "fetch_instrumentation_score_rules", "tool"
    ) as span:
        try:
            # First, get the list of rule files
            rules_api_url = f"{GITHUB_API_BASE}/contents/rules"
            span.set_attribute("github.api_url", rules_api_url)
            span.set_attribute(
                MCPAttributes.MCP_TOOL_NAME, "get_instrumentation_score_rules"
            )

            if rule_ids:
                span.set_attribute("filter.rule_ids", ",".join(rule_ids))
            if impact_levels:
                span.set_attribute("filter.impact_levels", ",".join(impact_levels))
            if targets:
                span.set_attribute("filter.targets", ",".join(targets))

            # Get list of rule files
            response = requests.get(rules_api_url, timeout=30)
            if response.status_code != 200:
                error_msg = (
                    f"Failed to fetch rules directory: HTTP {response.status_code}"
                )
                span.record_exception(Exception(error_msg))
                raise Exception(error_msg)

            files_data = response.json()

            # Filter rule files (exclude template and non-rule files)
            rule_files = [
                f
                for f in files_data
                if f["name"].endswith(".md") and not f["name"].startswith("_")
            ]

            # Filter by specific rule IDs if provided
            if rule_ids:
                rule_files = [
                    f
                    for f in rule_files
                    if any(f["name"].startswith(rule_id) for rule_id in rule_ids)
                ]

            span.set_attribute("rules.total_files", len(rule_files))

            # Fetch rule contents
            rules = {}
            fetched_count = 0
            filtered_count = 0

            for rule_file in rule_files:
                try:
                    result = _fetch_single_rule(rule_file, impact_levels, targets)
                    if result is None:  # Filtered out
                        filtered_count += 1
                        continue

                    rule_id, rule_content = result
                    rules[rule_id] = rule_content
                    fetched_count += 1

                except Exception as e:
                    logger.warning(f"Failed to fetch rule {rule_file['name']}: {e}")
                    continue

            span.set_attribute("rules.fetched_count", fetched_count)
            span.set_attribute("rules.filtered_count", filtered_count)

            logger.info(
                f"Successfully fetched {fetched_count} instrumentation score rules"
            )

            return {
                "rules": rules,
                "metadata": {
                    "total_available": len(rule_files),
                    "fetched": fetched_count,
                    "filtered_out": filtered_count,
                    "filters_applied": {
                        "rule_ids": rule_ids,
                        "impact_levels": impact_levels,
                        "targets": targets,
                    },
                },
            }

        except Exception as e:
            add_enhanced_error_attributes(span, e, fetch_rules_error="true")
            logger.error(f"Error fetching instrumentation score rules: {e}")
            raise


def _fetch_single_rule(
    rule_file: Dict[str, Any],
    impact_levels: Optional[List[str]] = None,
    targets: Optional[List[str]] = None,
) -> Optional[tuple[str, Dict[str, Any]]]:
    """
    Fetch and parse a single rule file.

    Args:
        rule_file: Rule file metadata from GitHub API
        impact_levels: Optional impact level filter
        targets: Optional target filter

    Returns:
        Tuple of (rule_id, rule_data) or None if filtered out
    """
    try:
        rule_url = rule_file["download_url"]

        response = requests.get(rule_url, timeout=30)
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}")

        content = response.text
        rule_data = _parse_rule_content(content)

        # Apply filters
        if impact_levels and rule_data.get("impact") not in impact_levels:
            return None

        if targets and rule_data.get("target") not in targets:
            return None

        rule_id = rule_data.get("id", rule_file["name"].replace(".md", ""))

        return rule_id, {
            **rule_data,
            "file_name": rule_file["name"],
            "raw_content": content,
        }

    except Exception as e:
        raise Exception(f"Failed to fetch rule {rule_file['name']}: {e}")


def _parse_rule_content(content: str) -> Dict[str, Any]:
    """
    Parse rule markdown content into structured data.

    Args:
        content: Raw markdown content of the rule

    Returns:
        Dict containing parsed rule data
    """
    lines = content.strip().split("\n")
    rule_data = {}

    for line in lines:
        line = line.strip()
        if line.startswith("**Rule ID:**"):
            rule_data["id"] = line.replace("**Rule ID:**", "").strip()
        elif line.startswith("**Description:**"):
            rule_data["description"] = line.replace("**Description:**", "").strip()
        elif line.startswith("**Rationale:**"):
            rule_data["rationale"] = line.replace("**Rationale:**", "").strip()
        elif line.startswith("**Target:**"):
            rule_data["target"] = line.replace("**Target:**", "").strip()
        elif line.startswith("**Criteria:**"):
            rule_data["criteria"] = line.replace("**Criteria:**", "").strip()
        elif line.startswith("**Impact:**"):
            rule_data["impact"] = line.replace("**Impact:**", "").strip()

    return rule_data
