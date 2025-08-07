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
Cache abstraction layer for OpenTelemetry Instrumentation MCP Server.

Provides pluggable caching implementations including in-memory and Redis-based caching.
Redis caching is optional and disabled by default.
"""

import json
import os
import time
import hashlib
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union
try:
    from opentelemetry.semconv.trace import SpanAttributes
except ImportError:
    # Fallback for when OpenTelemetry is not available
    class SpanAttributes:
        CODE_FUNCTION = "code.function"

from .telemetry import get_tracer, get_logger, add_span_attributes, set_span_error

tracer = get_tracer()
logger = get_logger()


class CacheBackend(ABC):
    """Abstract base class for cache backends."""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with optional TTL in seconds."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        pass

    @abstractmethod
    async def clear(self) -> bool:
        """Clear all cache entries."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check cache backend health."""
        pass


class InMemoryCache(CacheBackend):
    """Simple in-memory cache implementation."""

    def __init__(self, default_ttl: int = 3600):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.default_ttl = default_ttl

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key in self.cache:
            entry = self.cache[key]
            if entry["expires_at"] > time.time():
                return entry["value"]
            else:
                # Expired, remove it
                del self.cache[key]
        return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with TTL."""
        expires_at = time.time() + (ttl or self.default_ttl)
        self.cache[key] = {"value": value, "expires_at": expires_at}
        return True

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if key in self.cache:
            del self.cache[key]
            return True
        return False

    async def clear(self) -> bool:
        """Clear all cache entries."""
        self.cache.clear()
        return True

    async def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return await self.get(key) is not None

    async def health_check(self) -> Dict[str, Any]:
        """Check in-memory cache health."""
        # Clean up expired entries
        current_time = time.time()
        expired_keys = [
            key
            for key, entry in self.cache.items()
            if entry["expires_at"] <= current_time
        ]
        for key in expired_keys:
            del self.cache[key]

        return {
            "status": "healthy",
            "backend": "in_memory",
            "entries": len(self.cache),
            "expired_cleaned": len(expired_keys),
        }


class RedisCache(CacheBackend):
    """Redis-based cache implementation."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        default_ttl: int = 3600,
        key_prefix: str = "otel_mcp:",
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.default_ttl = default_ttl
        self.key_prefix = key_prefix
        self._redis = None

    async def _get_redis(self):
        """Get Redis connection, creating it if needed."""
        if self._redis is None:
            try:
                import redis.asyncio as redis
            except ImportError:
                raise ImportError(
                    "redis package is required for Redis caching. Install with: pip install redis"
                )

            try:
                self._redis = redis.Redis(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    password=self.password,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                )
                # Test connection
                await self._redis.ping()
                logger.info(
                    "Redis connection established",
                    extra={
                        "host": self.host,
                        "port": self.port,
                        "db": self.db,
                    },
                )
            except Exception as e:
                logger.error(
                    "Failed to connect to Redis",
                    exc_info=True,
                    extra={
                        "host": self.host,
                        "port": self.port,
                        "error": str(e),
                    },
                )
                raise
        return self._redis

    def _make_key(self, key: str) -> str:
        """Create prefixed cache key."""
        return f"{self.key_prefix}{key}"

    async def get(self, key: str) -> Optional[Any]:
        """Get value from Redis cache."""
        try:
            redis_client = await self._get_redis()
            value = await redis_client.get(self._make_key(key))
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning(
                "Redis get operation failed, falling back",
                extra={"key": key, "error": str(e)},
            )
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in Redis cache with TTL."""
        try:
            redis_client = await self._get_redis()
            serialized_value = json.dumps(value, default=str)
            result = await redis_client.setex(
                self._make_key(key), ttl or self.default_ttl, serialized_value
            )
            return result
        except Exception as e:
            logger.warning(
                "Redis set operation failed",
                extra={"key": key, "error": str(e)},
            )
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from Redis cache."""
        try:
            redis_client = await self._get_redis()
            result = await redis_client.delete(self._make_key(key))
            return result > 0
        except Exception as e:
            logger.warning(
                "Redis delete operation failed",
                extra={"key": key, "error": str(e)},
            )
            return False

    async def clear(self) -> bool:
        """Clear all cache entries with our prefix."""
        try:
            redis_client = await self._get_redis()
            keys = await redis_client.keys(f"{self.key_prefix}*")
            if keys:
                result = await redis_client.delete(*keys)
                return result > 0
            return True
        except Exception as e:
            logger.warning("Redis clear operation failed", extra={"error": str(e)})
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis cache."""
        try:
            redis_client = await self._get_redis()
            result = await redis_client.exists(self._make_key(key))
            return result > 0
        except Exception as e:
            logger.warning(
                "Redis exists operation failed",
                extra={"key": key, "error": str(e)},
            )
            return False

    async def health_check(self) -> Dict[str, Any]:
        """Check Redis cache health."""
        try:
            redis_client = await self._get_redis()
            info = await redis_client.info()
            await redis_client.ping()

            return {
                "status": "healthy",
                "backend": "redis",
                "host": self.host,
                "port": self.port,
                "db": self.db,
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "redis_version": info.get("redis_version", "unknown"),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "backend": "redis",
                "host": self.host,
                "port": self.port,
                "error": str(e),
            }


class CacheManager:
    """Cache manager that handles cache operations with telemetry."""

    def __init__(self, backend: CacheBackend):
        self.backend = backend

    def _generate_cache_key(
        self,
        operation: str,
        language: Optional[str] = None,
        version: Optional[str] = None,
        category: Optional[str] = None,
        repo: Optional[str] = None,
        keywords: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Generate a consistent cache key for the operation."""
        key_parts = [operation]

        if language:
            key_parts.append(f"lang:{language}")
        if version:
            key_parts.append(f"ver:{version}")
        if category:
            key_parts.append(f"cat:{category}")
        if repo:
            key_parts.append(f"repo:{repo}")
        if keywords:
            # Hash keywords to avoid key length issues
            keywords_hash = hashlib.md5(keywords.encode()).hexdigest()[:8]
            key_parts.append(f"kw:{keywords_hash}")

        # Add any additional parameters
        for key, value in sorted(kwargs.items()):
            if value is not None:
                key_parts.append(f"{key}:{value}")

        cache_key = ":".join(key_parts)
        return cache_key

    async def get_or_set(
        self,
        operation: str,
        fetch_func,
        ttl: Optional[int] = None,
        language: Optional[str] = None,
        version: Optional[str] = None,
        category: Optional[str] = None,
        repo: Optional[str] = None,
        keywords: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """Get from cache or fetch and cache the result."""
        cache_key = self._generate_cache_key(
            operation=operation,
            language=language,
            version=version,
            category=category,
            repo=repo,
            keywords=keywords,
            **kwargs,
        )

        with tracer.start_as_current_span("cache.get_or_set") as span:
            add_span_attributes(
                span,
                **{
                    SpanAttributes.CODE_FUNCTION: "get_or_set",
                    "cache.operation": operation,
                    "cache.key": cache_key,
                    "cache.backend": self.backend.__class__.__name__,
                },
            )

            try:
                # Try to get from cache first
                cached_result = await self.backend.get(cache_key)
                if cached_result is not None:
                    span.add_event(
                        "cache_hit",
                        {
                            "cache.key": cache_key,
                            "cache.operation": operation,
                        },
                    )
                    logger.debug(
                        "Cache hit",
                        extra={
                            "operation": operation,
                            "cache_key": cache_key,
                        },
                    )
                    return cached_result

                # Cache miss - fetch the data
                span.add_event(
                    "cache_miss",
                    {
                        "cache.key": cache_key,
                        "cache.operation": operation,
                    },
                )

                logger.debug(
                    "Cache miss, fetching data",
                    extra={
                        "operation": operation,
                        "cache_key": cache_key,
                    },
                )

                # Call the fetch function
                result = await fetch_func()

                # Cache the result
                cache_success = await self.backend.set(cache_key, result, ttl)
                span.add_event(
                    "cache_set",
                    {
                        "cache.key": cache_key,
                        "cache.operation": operation,
                        "cache.success": cache_success,
                    },
                )

                if cache_success:
                    logger.debug(
                        "Data cached successfully",
                        extra={
                            "operation": operation,
                            "cache_key": cache_key,
                        },
                    )
                else:
                    logger.warning(
                        "Failed to cache data",
                        extra={
                            "operation": operation,
                            "cache_key": cache_key,
                        },
                    )

                return result

            except Exception as e:
                set_span_error(span, e)
                logger.error(
                    "Cache operation failed",
                    exc_info=True,
                    extra={
                        "operation": operation,
                        "cache_key": cache_key,
                    },
                )
                # If caching fails, still try to fetch the data
                return await fetch_func()

    async def invalidate(
        self,
        operation: str,
        language: Optional[str] = None,
        version: Optional[str] = None,
        category: Optional[str] = None,
        repo: Optional[str] = None,
        keywords: Optional[str] = None,
        **kwargs,
    ) -> bool:
        """Invalidate a specific cache entry."""
        cache_key = self._generate_cache_key(
            operation=operation,
            language=language,
            version=version,
            category=category,
            repo=repo,
            keywords=keywords,
            **kwargs,
        )

        with tracer.start_as_current_span("cache.invalidate") as span:
            add_span_attributes(
                span,
                **{
                    SpanAttributes.CODE_FUNCTION: "invalidate",
                    "cache.operation": operation,
                    "cache.key": cache_key,
                },
            )

            try:
                result = await self.backend.delete(cache_key)
                span.add_event(
                    "cache_invalidated",
                    {
                        "cache.key": cache_key,
                        "cache.success": result,
                    },
                )
                return result
            except Exception as e:
                set_span_error(span, e)
                logger.error(
                    "Cache invalidation failed",
                    exc_info=True,
                    extra={"cache_key": cache_key},
                )
                return False

    async def health_check(self) -> Dict[str, Any]:
        """Check cache health."""
        return await self.backend.health_check()


def create_cache_manager() -> CacheManager:
    """Create cache manager based on configuration."""
    cache_enabled = os.getenv("CACHE_ENABLED", "false").lower() == "true"
    cache_backend = os.getenv("CACHE_BACKEND", "memory").lower()

    if not cache_enabled:
        logger.info("Caching is disabled, using in-memory cache with short TTL")
        backend = InMemoryCache(default_ttl=60)  # Very short TTL when disabled
        return CacheManager(backend)

    if cache_backend == "redis":
        try:
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_db = int(os.getenv("REDIS_DB", "0"))
            redis_password = os.getenv("REDIS_PASSWORD")
            default_ttl = int(os.getenv("CACHE_DEFAULT_TTL", "3600"))
            key_prefix = os.getenv("CACHE_KEY_PREFIX", "otel_mcp:")

            backend = RedisCache(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                default_ttl=default_ttl,
                key_prefix=key_prefix,
            )
            logger.info(
                "Redis cache enabled",
                extra={
                    "host": redis_host,
                    "port": redis_port,
                    "db": redis_db,
                    "default_ttl": default_ttl,
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to initialize Redis cache, falling back to in-memory",
                exc_info=True,
            )
            backend = InMemoryCache()
    else:
        default_ttl = int(os.getenv("CACHE_DEFAULT_TTL", "3600"))
        backend = InMemoryCache(default_ttl=default_ttl)
        logger.info(
            "In-memory cache enabled", extra={"default_ttl": default_ttl}
        )

    return CacheManager(backend)


# Global cache manager instance
cache_manager = create_cache_manager()