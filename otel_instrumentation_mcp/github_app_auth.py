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
GitHub App authentication module for OpenTelemetry MCP Server.

This module provides GitHub App authentication using JWT tokens and installation access tokens.
It includes comprehensive OpenTelemetry tracing for all authentication operations.
"""

import os
import time
import jwt
import httpx
from typing import Optional, Dict, Any, ClassVar
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
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

tracer = get_tracer()
logger = get_logger()


@dataclass
class GitHubAppConfig:
    """Configuration for GitHub App authentication."""

    app_id: str
    installation_id: str
    private_key_path: str
    jwt_expiry_seconds: int = 600
    token_refresh_buffer_minutes: int = 5
    api_version: str = "2022-11-28"
    user_agent: str = "otel-instrumentation-mcp-server"

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.app_id.isdigit():
            raise ValueError("GITHUB_APP_ID must be numeric")
        if not self.installation_id.isdigit():
            raise ValueError("GITHUB_INSTALLATION_ID must be numeric")
        if not os.path.exists(self.private_key_path):
            raise ValueError(f"Private key file not found: {self.private_key_path}")


class GitHubAppAuthError(Exception):
    """Custom exception for GitHub App authentication errors."""

    pass


class GitHubAppAuth:
    """
    GitHub App authentication handler with OpenTelemetry tracing.

    Handles JWT generation and installation access token retrieval for GitHub App authentication.
    All operations are traced with comprehensive telemetry data.
    """

    _DEFAULT_TIMEOUT: ClassVar[int] = 30
    _MAX_RETRIES: ClassVar[int] = 3

    def __init__(self, config: Optional[GitHubAppConfig] = None):
        """Initialize GitHub App authentication."""
        self._config: Optional[GitHubAppConfig] = config or self._load_config_from_env()
        self._installation_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._private_key: Optional[str] = None
        self._http_client: Optional[httpx.AsyncClient] = None

        if self._config:
            self._private_key = self._load_private_key()
            logger.info(
                "GitHub App authentication initialized",
                extra={
                    "app_id": self._config.app_id,
                    "installation_id": self._config.installation_id,
                },
            )

    def _load_config_from_env(self) -> Optional[GitHubAppConfig]:
        """Load configuration from environment variables."""
        app_id = os.getenv("GITHUB_APP_ID")
        installation_id = os.getenv("GITHUB_INSTALLATION_ID")
        private_key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")

        if not all([app_id, installation_id, private_key_path]):
            missing = [
                var
                for var, val in [
                    ("GITHUB_APP_ID", app_id),
                    ("GITHUB_INSTALLATION_ID", installation_id),
                    ("GITHUB_APP_PRIVATE_KEY_PATH", private_key_path),
                ]
                if not val
            ]
            logger.warning(
                "GitHub App authentication not configured - missing environment variables",
                extra={"missing_variables": missing},
            )
            return None

        try:
            return GitHubAppConfig(
                app_id=app_id,
                installation_id=installation_id,
                private_key_path=private_key_path,
            )
        except ValueError as e:
            logger.error(f"Invalid GitHub App configuration: {e}")
            return None

    def _load_private_key(self) -> str:
        """Load and validate private key from file."""
        if not self._config:
            raise GitHubAppAuthError("No configuration available")

        try:
            with open(self._config.private_key_path, "r") as key_file:
                private_key = key_file.read().strip()

            if not private_key.startswith("-----BEGIN") or not private_key.endswith(
                "-----"
            ):
                raise GitHubAppAuthError("Invalid private key format")

            logger.debug("GitHub App private key loaded successfully")
            return private_key

        except Exception as e:
            logger.error(f"Failed to load GitHub App private key: {e}")
            raise GitHubAppAuthError(f"Failed to load private key: {e}")

    def _generate_jwt(self) -> str:
        """Generate JWT token for GitHub App authentication."""
        if not self._config or not self._private_key:
            raise GitHubAppAuthError("GitHub App not properly configured")

        try:
            now = int(time.time())
            expires_at = now + self._config.jwt_expiry_seconds

            payload = {
                "iat": now,
                "exp": expires_at,
                "iss": self._config.app_id,
            }

            jwt_token = jwt.encode(payload, self._private_key, algorithm="RS256")
            logger.debug(
                f"GitHub App JWT token generated for app {self._config.app_id}"
            )
            return jwt_token

        except Exception as e:
            logger.error(f"Failed to generate GitHub App JWT: {e}")
            raise GitHubAppAuthError(f"Failed to generate JWT: {e}")

    async def _get_installation_access_token(self) -> str:
        """Get installation access token using JWT with retry logic."""
        if not self._config:
            raise GitHubAppAuthError("GitHub App not configured")

        jwt_token = self._generate_jwt()
        url = f"https://api.github.com/app/installations/{self._config.installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self._config.api_version,
            "User-Agent": self._config.user_agent,
        }

        if not self._http_client:
            self._http_client = httpx.AsyncClient(
                timeout=self._DEFAULT_TIMEOUT,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )

        for attempt in range(self._MAX_RETRIES):
            try:
                logger.info(
                    f"Requesting GitHub App installation access token (attempt {attempt + 1})"
                )

                response = await self._http_client.post(url, headers=headers)
                response.raise_for_status()
                token_data = response.json()

                access_token = token_data["token"]
                expires_at = datetime.fromisoformat(
                    token_data["expires_at"].replace("Z", "+00:00")
                ).replace(tzinfo=timezone.utc)

                self._installation_token = access_token
                self._token_expires_at = expires_at

                logger.info(
                    "GitHub App installation access token received",
                    extra={
                        "installation_id": self._config.installation_id,
                        "expires_at": expires_at.isoformat(),
                        "permissions": list(token_data.get("permissions", {}).keys()),
                    },
                )
                return access_token

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401 or attempt == self._MAX_RETRIES - 1:
                    raise GitHubAppAuthError(
                        f"Failed to get installation access token: {e}"
                    )
                logger.warning(f"HTTP error on attempt {attempt + 1}: {e}, retrying...")
                await httpx.AsyncClient().aclose()

            except Exception as e:
                if attempt == self._MAX_RETRIES - 1:
                    raise GitHubAppAuthError(
                        f"Failed to get installation access token: {e}"
                    )
                logger.warning(f"Error on attempt {attempt + 1}: {e}, retrying...")

    async def get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for GitHub API requests."""
        if not self._config:
            github_token = os.getenv("GITHUB_TOKEN")
            if github_token:
                logger.debug("GitHub App not configured, using personal token")
                return {
                    "Authorization": f"token {github_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": (
                        self._config.api_version if self._config else "2022-11-28"
                    ),
                    "User-Agent": (
                        self._config.user_agent
                        if self._config
                        else "otel-instrumentation-mcp-server/0.10.0"
                    ),
                }
            raise GitHubAppAuthError("No GitHub authentication configured")

        # Check if we need to refresh the installation token
        now = datetime.now(timezone.utc)
        buffer = timedelta(minutes=self._config.token_refresh_buffer_minutes)

        if (
            not self._installation_token
            or not self._token_expires_at
            or now >= self._token_expires_at - buffer
        ):
            logger.debug("Refreshing GitHub App installation access token")
            await self._get_installation_access_token()

        return {
            "Authorization": f"token {self._installation_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self._config.api_version,
            "User-Agent": self._config.user_agent,
        }

    @property
    def is_configured(self) -> bool:
        """Check if GitHub App authentication is properly configured."""
        return self._config is not None and self._private_key is not None

    def get_auth_info(self) -> Dict[str, Any]:
        """Get authentication information for debugging/monitoring."""
        return {
            "configured": self.is_configured,
            "auth_type": "github_app" if self.is_configured else "personal_token",
            "app_id": self._config.app_id if self._config else None,
            "installation_id": self._config.installation_id if self._config else None,
            "has_cached_token": bool(self._installation_token),
            "token_expires_at": (
                self._token_expires_at.isoformat() if self._token_expires_at else None
            ),
        }

    async def close(self) -> None:
        """Clean up resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


def create_github_app_auth(config: Optional[GitHubAppConfig] = None) -> GitHubAppAuth:
    """Factory function to create GitHubAppAuth instances."""
    return GitHubAppAuth(config)


# Global instance for backward compatibility - consider using factory function instead
github_app_auth = GitHubAppAuth()
