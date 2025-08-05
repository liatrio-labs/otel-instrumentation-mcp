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
Version resolution utilities for GitHub repositories.

This module provides centralized version resolution for GitHub repositories,
supporting semantic versioning, caching, and comprehensive telemetry.
"""

import os
import re
import time
import asyncio
import requests
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Span

from .telemetry import (
    get_tracer,
    get_logger,
    add_span_attributes,
    set_span_error,
    VCSAttributes,
)

tracer = get_tracer()
logger = get_logger()


class VersionStrategy(Enum):
    """Version resolution strategies for different repositories."""

    RELEASES_ONLY = "releases_only"
    TAGS_ONLY = "tags_only"
    RELEASES_WITH_FALLBACK = "releases_with_fallback"
    TAGS_WITH_FALLBACK = "tags_with_fallback"


@dataclass
class VersionInfo:
    """Information about a resolved version."""

    resolved_version: str
    ref_type: str  # "branch", "tag", "release"
    resolution_source: str  # "releases_api", "tags_api", "fallback"
    is_semantic: bool
    commit_sha: Optional[str] = None


class VersionCache:
    """Simple in-memory cache for version resolution."""

    def __init__(self, ttl_seconds: int = 300):  # 5 minute TTL
        self.cache: Dict[str, Tuple[Any, float]] = {}
        self.ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            else:
                del self.cache[key]
        return None

    def set(self, key: str, value: Any) -> None:
        """Set value in cache with current timestamp."""
        self.cache[key] = (value, time.time())

    def clear(self) -> None:
        """Clear all cached values."""
        self.cache.clear()


# Global cache instance
_version_cache = VersionCache()


class GitHubVersionResolver:
    """Centralized version resolution for GitHub repositories."""

    def __init__(self, repo_config: Dict[str, Any]):
        self.config = repo_config
        self.repo_owner = repo_config["owner"]
        self.repo_name = repo_config["name"]
        self.repo_full_name = f"{self.repo_owner}/{self.repo_name}"
        self.strategy = VersionStrategy(
            repo_config.get("version_strategy", "releases_with_fallback")
        )

        # GitHub API configuration
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.headers = {"Accept": "application/vnd.github+json"}
        if self.github_token:
            self.headers["Authorization"] = f"Bearer {self.github_token}"

    async def resolve_version(self, version: Optional[str] = None) -> VersionInfo:
        """Resolve version string to specific version information."""
        with tracer.start_as_current_span("version_resolver.resolve_version") as span:
            try:
                add_span_attributes(
                    span,
                    **{
                        "version.requested": version or "latest",
                        "version.strategy": self.strategy.value,
                        "github.repository": self.repo_full_name,
                    },
                )

                # Check cache first
                cache_key = f"{self.repo_full_name}:{version or 'latest'}"
                cached_result = _version_cache.get(cache_key)
                if cached_result:
                    span.add_event("version_cache_hit", {"cache_key": cache_key})
                    return cached_result

                # Resolve version based on strategy
                if not version or version.lower() in ("latest", "main", "master"):
                    version_info = await self._resolve_latest_version(span)
                else:
                    try:
                        version_info = await self._resolve_specific_version(
                            span, version
                        )
                    except ValueError:
                        # If specific version resolution fails, fall back to main
                        logger.warning(
                            f"Could not resolve version {version}, falling back to main"
                        )
                        version_info = VersionInfo(
                            resolved_version="main",
                            ref_type="branch",
                            resolution_source="fallback",
                            is_semantic=False,
                        )

                # Cache the result
                _version_cache.set(cache_key, version_info)

                add_span_attributes(
                    span,
                    **{
                        "version.resolved": version_info.resolved_version,
                        "version.ref_type": version_info.ref_type,
                        "version.source": version_info.resolution_source,
                        "version.is_semantic": version_info.is_semantic,
                    },
                )

                span.add_event(
                    "version_resolved",
                    {
                        "requested": version or "latest",
                        "resolved": version_info.resolved_version,
                        "source": version_info.resolution_source,
                    },
                )

                return version_info

            except Exception as e:
                set_span_error(span, e)
                logger.error(
                    "Failed to resolve version",
                    exc_info=True,
                    extra={
                        "repository": self.repo_full_name,
                        "version": version,
                        "strategy": self.strategy.value,
                    },
                )
                # Fallback to main branch
                return VersionInfo(
                    resolved_version="main",
                    ref_type="branch",
                    resolution_source="fallback",
                    is_semantic=False,
                )

    async def _resolve_latest_version(self, span: Span) -> VersionInfo:
        """Resolve latest version based on strategy."""
        if self.strategy in (
            VersionStrategy.RELEASES_ONLY,
            VersionStrategy.RELEASES_WITH_FALLBACK,
        ):
            try:
                return await self._get_latest_release(span)
            except Exception as e:
                if self.strategy == VersionStrategy.RELEASES_ONLY:
                    raise
                logger.warning(
                    f"Failed to get latest release, falling back to tags: {e}"
                )

        if self.strategy in (
            VersionStrategy.TAGS_ONLY,
            VersionStrategy.TAGS_WITH_FALLBACK,
        ):
            try:
                return await self._get_latest_tag(span)
            except Exception as e:
                if self.strategy == VersionStrategy.TAGS_ONLY:
                    raise
                logger.warning(f"Failed to get latest tag, falling back to main: {e}")

        # Final fallback to main branch
        return VersionInfo(
            resolved_version="main",
            ref_type="branch",
            resolution_source="fallback",
            is_semantic=False,
        )

    async def _resolve_specific_version(self, span: Span, version: str) -> VersionInfo:
        """Resolve specific version string."""
        # Try to find exact match in releases first
        try:
            release_info = await self._get_release_by_tag(span, version)
            if release_info:
                return release_info
        except Exception:
            pass

        # Try to find in tags
        try:
            tag_info = await self._get_tag_info(span, version)
            if tag_info:
                return tag_info
        except Exception:
            pass

        # Only use version directly if it looks like a commit SHA or known branch names
        if self._is_commit_sha(version) or version in (
            "main",
            "master",
            "develop",
            "dev",
        ):
            return VersionInfo(
                resolved_version=version,
                ref_type="branch" if not self._is_commit_sha(version) else "commit",
                resolution_source="direct",
                is_semantic=self._is_semantic_version(version),
            )

        # Final fallback - raise error to trigger fallback in main resolve_version method
        raise ValueError(f"Could not resolve version: {version}")

    async def _get_latest_release(self, span: Span) -> VersionInfo:
        """Get latest release from GitHub API."""
        url = f"https://api.github.com/repos/{self.repo_full_name}/releases/latest"

        add_span_attributes(
            span,
            **{
                SpanAttributes.HTTP_METHOD: "GET",
                SpanAttributes.HTTP_URL: url,
            },
        )

        response = requests.get(url, headers=self.headers, timeout=10)

        add_span_attributes(
            span,
            **{
                SpanAttributes.HTTP_STATUS_CODE: response.status_code,
            },
        )

        if response.status_code == 404:
            raise ValueError("No releases found")

        response.raise_for_status()
        release_data = response.json()

        return VersionInfo(
            resolved_version=release_data["tag_name"],
            ref_type="tag",
            resolution_source="releases_api",
            is_semantic=self._is_semantic_version(release_data["tag_name"]),
            commit_sha=release_data.get("target_commitish"),
        )

    async def _get_latest_tag(self, span: Span) -> VersionInfo:
        """Get latest tag from GitHub API."""
        url = f"https://api.github.com/repos/{self.repo_full_name}/tags"

        add_span_attributes(
            span,
            **{
                SpanAttributes.HTTP_METHOD: "GET",
                SpanAttributes.HTTP_URL: url,
            },
        )

        response = requests.get(
            url, headers=self.headers, params={"per_page": 1}, timeout=10
        )

        add_span_attributes(
            span,
            **{
                SpanAttributes.HTTP_STATUS_CODE: response.status_code,
            },
        )

        response.raise_for_status()
        tags_data = response.json()

        if not tags_data:
            raise ValueError("No tags found")

        latest_tag = tags_data[0]
        return VersionInfo(
            resolved_version=latest_tag["name"],
            ref_type="tag",
            resolution_source="tags_api",
            is_semantic=self._is_semantic_version(latest_tag["name"]),
            commit_sha=latest_tag["commit"]["sha"],
        )

    async def _get_release_by_tag(self, span: Span, tag: str) -> Optional[VersionInfo]:
        """Get specific release by tag name."""
        url = f"https://api.github.com/repos/{self.repo_full_name}/releases/tags/{tag}"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 404:
                return None

            response.raise_for_status()
            release_data = response.json()

            return VersionInfo(
                resolved_version=release_data["tag_name"],
                ref_type="tag",
                resolution_source="releases_api",
                is_semantic=self._is_semantic_version(release_data["tag_name"]),
                commit_sha=release_data.get("target_commitish"),
            )
        except Exception:
            return None

    async def _get_tag_info(self, span: Span, tag: str) -> Optional[VersionInfo]:
        """Get specific tag information."""
        url = f"https://api.github.com/repos/{self.repo_full_name}/git/refs/tags/{tag}"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 404:
                return None

            response.raise_for_status()
            tag_data = response.json()

            return VersionInfo(
                resolved_version=tag,
                ref_type="tag",
                resolution_source="tags_api",
                is_semantic=self._is_semantic_version(tag),
                commit_sha=tag_data["object"]["sha"],
            )
        except Exception:
            return None

    def _is_semantic_version(self, version: str) -> bool:
        """Check if version string follows semantic versioning."""
        # Simple semantic version pattern: v1.2.3 or 1.2.3
        pattern = r"^v?(\d+)\.(\d+)\.(\d+)(?:-[\w\.-]+)?(?:\+[\w\.-]+)?$"
        return bool(re.match(pattern, version))

    def _is_valid_ref(self, ref: str) -> bool:
        """Check if string is a valid Git reference."""
        # Basic validation for Git refs
        if not ref or len(ref) > 250:
            return False
        # Avoid some invalid characters
        invalid_chars = [" ", "~", "^", ":", "?", "*", "[", "\\"]
        return not any(char in ref for char in invalid_chars)

    def _is_commit_sha(self, ref: str) -> bool:
        """Check if string looks like a commit SHA."""
        return bool(re.match(r"^[a-f0-9]{7,40}$", ref.lower()))

    def build_raw_url(self, path: str, version: str) -> str:
        """Build raw.githubusercontent.com URL with specific version."""
        return (
            f"https://raw.githubusercontent.com/{self.repo_full_name}/{version}/{path}"
        )

    def build_blob_url(self, path: str, version: str) -> str:
        """Build github.com blob URL with specific version."""
        return f"https://github.com/{self.repo_full_name}/blob/{version}/{path}"

    def build_api_url(self, endpoint: str = "") -> str:
        """Build GitHub API URL for this repository."""
        base = f"https://api.github.com/repos/{self.repo_full_name}"
        return f"{base}/{endpoint}" if endpoint else base

    def add_vcs_attributes_to_span(self, span: Span, version_info: VersionInfo) -> None:
        """Add comprehensive VCS attributes to span."""
        vcs_attributes = {
            # Repository identification
            VCSAttributes.VCS_REPOSITORY_NAME: self.config["name"],
            VCSAttributes.VCS_REPOSITORY_URL_FULL: self.config["url_full"],
            VCSAttributes.VCS_PROVIDER_NAME: self.config["provider"],
            VCSAttributes.VCS_OWNER_NAME: self.config["owner"],
            # Head reference (what we're using)
            VCSAttributes.VCS_REF_HEAD_NAME: version_info.resolved_version,
            VCSAttributes.VCS_REF_HEAD_REVISION: version_info.resolved_version,
            VCSAttributes.VCS_REF_HEAD_TYPE: version_info.ref_type,
            # Base reference (what we started from - typically main)
            VCSAttributes.VCS_REF_BASE_NAME: "main",
            VCSAttributes.VCS_REF_BASE_REVISION: "main",
            VCSAttributes.VCS_REF_BASE_TYPE: "branch",
        }

        # Add version resolution metadata
        vcs_attributes.update(
            {
                "vcs.resolution.source": version_info.resolution_source,
                "vcs.resolution.strategy": self.strategy.value,
                "vcs.resolution.is_semantic": version_info.is_semantic,
            }
        )

        if version_info.commit_sha:
            vcs_attributes["vcs.commit.sha"] = version_info.commit_sha

        add_span_attributes(span, **vcs_attributes)
