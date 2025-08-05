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

"""Tests for version resolution functionality."""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from otel_instrumentation_mcp.version_resolver import (
    GitHubVersionResolver,
    VersionInfo,
    VersionStrategy,
    _version_cache,
)
from otel_instrumentation_mcp.repo_configs import get_repo_config


class TestVersionResolver:
    """Test cases for GitHubVersionResolver."""

    def setup_method(self):
        """Set up test fixtures."""
        # Clear cache before each test
        _version_cache.clear()

        # Sample repository configuration
        self.repo_config = {
            "owner": "test-org",
            "name": "test-repo",
            "provider": "github",
            "url_full": "https://github.com/test-org/test-repo",
            "version_strategy": "releases_with_fallback",
        }

        self.resolver = GitHubVersionResolver(self.repo_config)

    def test_init(self):
        """Test resolver initialization."""
        assert self.resolver.repo_owner == "test-org"
        assert self.resolver.repo_name == "test-repo"
        assert self.resolver.repo_full_name == "test-org/test-repo"
        assert self.resolver.strategy == VersionStrategy.RELEASES_WITH_FALLBACK

    def test_is_semantic_version(self):
        """Test semantic version detection."""
        # Valid semantic versions
        assert self.resolver._is_semantic_version("1.0.0")
        assert self.resolver._is_semantic_version("v1.0.0")
        assert self.resolver._is_semantic_version("2.1.3")
        assert self.resolver._is_semantic_version("1.0.0-alpha")
        assert self.resolver._is_semantic_version("1.0.0+build.1")

        # Invalid semantic versions
        assert not self.resolver._is_semantic_version("1.0")
        assert not self.resolver._is_semantic_version("main")
        assert not self.resolver._is_semantic_version("feature-branch")
        assert not self.resolver._is_semantic_version("")

    def test_is_valid_ref(self):
        """Test Git reference validation."""
        # Valid refs
        assert self.resolver._is_valid_ref("main")
        assert self.resolver._is_valid_ref("feature-branch")
        assert self.resolver._is_valid_ref("v1.0.0")
        assert self.resolver._is_valid_ref("abc123def")

        # Invalid refs
        assert not self.resolver._is_valid_ref("")
        assert not self.resolver._is_valid_ref("branch with spaces")
        assert not self.resolver._is_valid_ref("branch~with~tildes")
        assert not self.resolver._is_valid_ref("a" * 300)  # Too long

    def test_is_commit_sha(self):
        """Test commit SHA detection."""
        # Valid commit SHAs
        assert self.resolver._is_commit_sha("abc123def")
        assert self.resolver._is_commit_sha("1234567890abcdef")
        assert self.resolver._is_commit_sha("a" * 40)  # Full SHA

        # Invalid commit SHAs
        assert not self.resolver._is_commit_sha("main")
        assert not self.resolver._is_commit_sha("v1.0.0")
        assert not self.resolver._is_commit_sha("abc123")  # Too short
        assert not self.resolver._is_commit_sha("xyz123def")  # Invalid chars

    def test_build_urls(self):
        """Test URL building methods."""
        version = "v1.0.0"
        path = "docs/readme.md"

        raw_url = self.resolver.build_raw_url(path, version)
        expected_raw = (
            f"https://raw.githubusercontent.com/test-org/test-repo/{version}/{path}"
        )
        assert raw_url == expected_raw

        blob_url = self.resolver.build_blob_url(path, version)
        expected_blob = f"https://github.com/test-org/test-repo/blob/{version}/{path}"
        assert blob_url == expected_blob

        api_url = self.resolver.build_api_url("releases")
        expected_api = "https://api.github.com/repos/test-org/test-repo/releases"
        assert api_url == expected_api

    @pytest.mark.asyncio
    async def test_resolve_version_latest(self):
        """Test resolving latest version."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tag_name": "v1.2.3",
            "target_commitish": "abc123",
        }

        with patch("requests.get", return_value=mock_response):
            version_info = await self.resolver.resolve_version()

            assert version_info.resolved_version == "v1.2.3"
            assert version_info.ref_type == "tag"
            assert version_info.resolution_source == "releases_api"
            assert version_info.is_semantic is True
            assert version_info.commit_sha == "abc123"

    @pytest.mark.asyncio
    async def test_resolve_version_specific(self):
        """Test resolving specific version."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tag_name": "v1.0.0",
            "target_commitish": "def456",
        }

        with patch("requests.get", return_value=mock_response):
            version_info = await self.resolver.resolve_version("v1.0.0")

            assert version_info.resolved_version == "v1.0.0"
            assert version_info.ref_type == "tag"
            assert version_info.resolution_source == "releases_api"

    @pytest.mark.asyncio
    async def test_resolve_version_fallback(self):
        """Test fallback to main branch when version not found."""
        # Mock 404 response for releases
        mock_response_404 = Mock()
        mock_response_404.status_code = 404
        mock_response_404.raise_for_status.side_effect = Exception("Not found")

        with patch("requests.get", return_value=mock_response_404):
            version_info = await self.resolver.resolve_version("nonexistent")

            assert version_info.resolved_version == "main"
            assert version_info.ref_type == "branch"
            assert version_info.resolution_source == "fallback"

    @pytest.mark.asyncio
    async def test_resolve_version_caching(self):
        """Test version resolution caching."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tag_name": "v1.2.3",
            "target_commitish": "abc123",
        }

        with patch("requests.get", return_value=mock_response) as mock_get:
            # First call should hit the API
            version_info1 = await self.resolver.resolve_version("v1.2.3")
            assert mock_get.call_count == 1

            # Second call should use cache
            version_info2 = await self.resolver.resolve_version("v1.2.3")
            assert mock_get.call_count == 1  # No additional API call

            # Results should be identical
            assert version_info1.resolved_version == version_info2.resolved_version

    def test_add_vcs_attributes_to_span(self):
        """Test adding VCS attributes to span."""
        mock_span = Mock()
        version_info = VersionInfo(
            resolved_version="v1.0.0",
            ref_type="tag",
            resolution_source="releases_api",
            is_semantic=True,
            commit_sha="abc123",
        )

        with patch(
            "otel_instrumentation_mcp.version_resolver.add_span_attributes"
        ) as mock_add_attrs:
            self.resolver.add_vcs_attributes_to_span(mock_span, version_info)

            # Verify add_span_attributes was called
            mock_add_attrs.assert_called_once()

            # Check the attributes that were added
            call_args = mock_add_attrs.call_args
            attributes = call_args[1]  # kwargs

            assert attributes["vcs.repository.name"] == "test-repo"
            assert (
                attributes["vcs.repository.url.full"]
                == "https://github.com/test-org/test-repo"
            )
            assert attributes["vcs.provider.name"] == "github"
            assert attributes["vcs.owner.name"] == "test-org"
            assert attributes["vcs.ref.head.name"] == "v1.0.0"
            assert attributes["vcs.ref.head.revision"] == "v1.0.0"
            assert attributes["vcs.ref.head.type"] == "tag"
            assert attributes["vcs.commit.sha"] == "abc123"


class TestRepoConfigs:
    """Test cases for repository configurations."""

    def test_get_repo_config_valid(self):
        """Test getting valid repository configuration."""
        config = get_repo_config("opentelemetry-docs")

        assert config["owner"] == "open-telemetry"
        assert config["name"] == "opentelemetry.io"
        assert config["provider"] == "github"
        assert "url_full" in config
        assert "version_strategy" in config

    def test_get_repo_config_invalid(self):
        """Test getting invalid repository configuration."""
        with pytest.raises(KeyError):
            get_repo_config("nonexistent-repo")

    def test_repo_config_immutability(self):
        """Test that returned config is a copy (immutable)."""
        config1 = get_repo_config("opentelemetry-docs")
        config2 = get_repo_config("opentelemetry-docs")

        # Modify one config
        config1["modified"] = True

        # Other config should be unaffected
        assert "modified" not in config2


class TestVersionCache:
    """Test cases for version caching."""

    def setup_method(self):
        """Set up test fixtures."""
        _version_cache.clear()

    def test_cache_set_get(self):
        """Test basic cache set and get operations."""
        key = "test-key"
        value = "test-value"

        # Initially empty
        assert _version_cache.get(key) is None

        # Set and get
        _version_cache.set(key, value)
        assert _version_cache.get(key) == value

    def test_cache_expiry(self):
        """Test cache expiry functionality."""
        # Create cache with very short TTL
        from otel_instrumentation_mcp.version_resolver import VersionCache

        short_cache = VersionCache(ttl_seconds=0.1)

        key = "test-key"
        value = "test-value"

        short_cache.set(key, value)
        assert short_cache.get(key) == value

        # Wait for expiry
        import time

        time.sleep(0.2)

        # Should be expired
        assert short_cache.get(key) is None

    def test_cache_clear(self):
        """Test cache clearing."""
        _version_cache.set("key1", "value1")
        _version_cache.set("key2", "value2")

        assert _version_cache.get("key1") == "value1"
        assert _version_cache.get("key2") == "value2"

        _version_cache.clear()

        assert _version_cache.get("key1") is None
        assert _version_cache.get("key2") is None


if __name__ == "__main__":
    pytest.main([__file__])
