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
Repository configurations for version-aware GitHub integrations.

This module defines the configuration for all GitHub repositories
that support version-based documentation and content retrieval.
"""

from typing import Dict, Any

# Repository configurations with VCS metadata and version strategies
REPO_CONFIGS: Dict[str, Dict[str, Any]] = {
    "opentelemetry-docs": {
        "owner": "open-telemetry",
        "name": "opentelemetry.io",
        "provider": "github",
        "url_full": "https://github.com/open-telemetry/opentelemetry.io",
        "default_paths": {
            "docs": "content/en/docs/languages",
            "demo": "content/en/docs/demo/services/_index.md",
        },
        "version_strategy": "releases_with_fallback",
        "description": "OpenTelemetry documentation website",
    },
    "semantic-conventions": {
        "owner": "open-telemetry",
        "name": "semantic-conventions",
        "provider": "github",
        "url_full": "https://github.com/open-telemetry/semantic-conventions",
        "default_paths": {"docs": "docs"},
        "version_strategy": "releases_only",
        "description": "OpenTelemetry semantic conventions",
    },
    "instrumentation-score": {
        "owner": "instrumentation-score",
        "name": "spec",
        "provider": "github",
        "url_full": "https://github.com/instrumentation-score/spec",
        "default_paths": {"spec": "spec.md", "rules": "rules"},
        "version_strategy": "tags_with_fallback",
        "description": "Instrumentation Score specification",
    },
    "opentelemetry-demo": {
        "owner": "open-telemetry",
        "name": "opentelemetry-demo",
        "provider": "github",
        "url_full": "https://github.com/open-telemetry/opentelemetry-demo",
        "default_paths": {"src": "src"},
        "version_strategy": "releases_with_fallback",
        "description": "OpenTelemetry demo application",
    },
}


def get_repo_config(repo_key: str) -> Dict[str, Any]:
    """Get repository configuration by key.

    Args:
        repo_key: Repository configuration key

    Returns:
        Repository configuration dictionary

    Raises:
        KeyError: If repository key is not found
    """
    if repo_key not in REPO_CONFIGS:
        raise KeyError(f"Repository configuration not found: {repo_key}")

    return REPO_CONFIGS[repo_key].copy()
