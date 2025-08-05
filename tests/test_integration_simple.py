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

"""Simple integration tests that don't require external dependencies."""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_repo_configs():
    """Test repository configurations can be loaded."""
    try:
        from otel_instrumentation_mcp.repo_configs import get_repo_config

        # Test getting specific config
        otel_config = get_repo_config("opentelemetry-docs")
        assert otel_config["owner"] == "open-telemetry"
        assert otel_config["name"] == "opentelemetry.io"
        assert otel_config["provider"] == "github"
        assert "url_full" in otel_config

        print("✅ Repository configurations test passed")

    except Exception as e:
        print(f"❌ Repository configurations test failed: {e}")
        raise


def test_telemetry_vcs_attributes():
    """Test VCS attributes are properly defined."""
    try:
        from otel_instrumentation_mcp.telemetry import VCSAttributes

        # Test that all expected attributes are defined
        expected_attrs = [
            "VCS_REPOSITORY_NAME",
            "VCS_REPOSITORY_URL_FULL",
            "VCS_PROVIDER_NAME",
            "VCS_OWNER_NAME",
            "VCS_REF_HEAD_NAME",
            "VCS_REF_HEAD_REVISION",
            "VCS_REF_HEAD_TYPE",
            "VCS_REF_BASE_NAME",
            "VCS_REF_BASE_REVISION",
            "VCS_REF_BASE_TYPE",
        ]

        for attr in expected_attrs:
            assert hasattr(VCSAttributes, attr), f"Missing attribute: {attr}"
            value = getattr(VCSAttributes, attr)
            assert isinstance(value, str), f"Attribute {attr} should be string"
            assert value.startswith(
                "vcs."
            ), f"Attribute {attr} should start with 'vcs.'"

        print("✅ VCS attributes test passed")

    except Exception as e:
        print(f"❌ VCS attributes test failed: {e}")
        raise


def test_version_strategy_enum():
    """Test version strategy enum is properly defined."""
    try:
        from otel_instrumentation_mcp.version_resolver import VersionStrategy

        # Test that all expected strategies are defined
        expected_strategies = [
            "RELEASES_ONLY",
            "TAGS_ONLY",
            "RELEASES_WITH_FALLBACK",
            "TAGS_WITH_FALLBACK",
        ]

        for strategy in expected_strategies:
            assert hasattr(VersionStrategy, strategy), f"Missing strategy: {strategy}"

        # Test enum values
        assert VersionStrategy.RELEASES_ONLY.value == "releases_only"
        assert VersionStrategy.TAGS_ONLY.value == "tags_only"
        assert VersionStrategy.RELEASES_WITH_FALLBACK.value == "releases_with_fallback"
        assert VersionStrategy.TAGS_WITH_FALLBACK.value == "tags_with_fallback"

        print("✅ Version strategy enum test passed")

    except Exception as e:
        print(f"❌ Version strategy enum test failed: {e}")
        raise


def test_version_info_dataclass():
    """Test VersionInfo dataclass is properly defined."""
    try:
        from otel_instrumentation_mcp.version_resolver import VersionInfo

        # Test creating VersionInfo instance
        version_info = VersionInfo(
            resolved_version="v1.0.0",
            ref_type="tag",
            resolution_source="releases_api",
            is_semantic=True,
            commit_sha="abc123",
        )

        assert version_info.resolved_version == "v1.0.0"
        assert version_info.ref_type == "tag"
        assert version_info.resolution_source == "releases_api"
        assert version_info.is_semantic is True
        assert version_info.commit_sha == "abc123"

        # Test optional field
        version_info_minimal = VersionInfo(
            resolved_version="main",
            ref_type="branch",
            resolution_source="fallback",
            is_semantic=False,
        )

        assert version_info_minimal.commit_sha is None

        print("✅ VersionInfo dataclass test passed")

    except Exception as e:
        print(f"❌ VersionInfo dataclass test failed: {e}")
        raise


def run_all_tests():
    """Run all simple integration tests."""
    print("Running simple integration tests...")

    tests = [
        test_repo_configs,
        test_telemetry_vcs_attributes,
        test_version_strategy_enum,
        test_version_info_dataclass,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"Test {test.__name__} failed: {e}")

    print(f"\n📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed!")
    else:
        print("❌ Some tests failed")


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
