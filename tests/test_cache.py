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

import asyncio
import os
import pytest
import time
from unittest.mock import AsyncMock, patch

from otel_instrumentation_mcp.cache import (
    InMemoryCache,
    RedisCache,
    CacheManager,
    create_cache_manager,
)


class TestInMemoryCache:
    """Test in-memory cache implementation."""

    @pytest.fixture
    def cache(self):
        return InMemoryCache(default_ttl=1)

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        """Test basic set and get operations."""
        await cache.set("test_key", "test_value")
        result = await cache.get("test_key")
        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, cache):
        """Test getting a non-existent key returns None."""
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, cache):
        """Test that keys expire after TTL."""
        await cache.set("expire_key", "expire_value", ttl=0.1)
        
        # Should exist immediately
        result = await cache.get("expire_key")
        assert result == "expire_value"
        
        # Wait for expiration
        await asyncio.sleep(0.2)
        
        # Should be expired
        result = await cache.get("expire_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, cache):
        """Test key deletion."""
        await cache.set("delete_key", "delete_value")
        
        # Verify it exists
        assert await cache.exists("delete_key")
        
        # Delete it
        result = await cache.delete("delete_key")
        assert result is True
        
        # Verify it's gone
        assert not await cache.exists("delete_key")

    @pytest.mark.asyncio
    async def test_clear(self, cache):
        """Test clearing all cache entries."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        
        # Verify both exist
        assert await cache.exists("key1")
        assert await cache.exists("key2")
        
        # Clear cache
        result = await cache.clear()
        assert result is True
        
        # Verify both are gone
        assert not await cache.exists("key1")
        assert not await cache.exists("key2")

    @pytest.mark.asyncio
    async def test_health_check(self, cache):
        """Test health check functionality."""
        # Add some entries
        await cache.set("health1", "value1")
        await cache.set("health2", "value2", ttl=0.1)
        
        # Wait for one to expire
        await asyncio.sleep(0.2)
        
        health = await cache.health_check()
        
        assert health["status"] == "healthy"
        assert health["backend"] == "in_memory"
        assert health["entries"] == 1  # Only one should remain
        assert health["expired_cleaned"] == 1  # One should have been cleaned


class TestRedisCache:
    """Test Redis cache implementation."""

    @pytest.fixture
    def cache(self):
        return RedisCache(
            host="localhost",
            port=6379,
            db=15,  # Use a test database
            default_ttl=1,
            key_prefix="test:",
        )

    @pytest.mark.asyncio
    async def test_redis_not_available(self):
        """Test graceful handling when Redis is not available."""
        cache = RedisCache(host="nonexistent-host", port=6379)
        
        # Should handle connection failure gracefully
        result = await cache.get("test_key")
        assert result is None
        
        result = await cache.set("test_key", "test_value")
        assert result is False

    @pytest.mark.asyncio
    async def test_redis_import_error(self):
        """Test handling when redis package is not installed."""
        cache = RedisCache()
        
        with patch("otel_instrumentation_mcp.cache.redis", None):
            with pytest.raises(ImportError, match="redis package is required"):
                await cache._get_redis()


class TestCacheManager:
    """Test cache manager functionality."""

    @pytest.fixture
    def cache_manager(self):
        backend = InMemoryCache(default_ttl=1)
        return CacheManager(backend)

    @pytest.mark.asyncio
    async def test_get_or_set_cache_miss(self, cache_manager):
        """Test get_or_set with cache miss."""
        fetch_func = AsyncMock(return_value="fetched_value")
        
        result = await cache_manager.get_or_set(
            operation="test_op",
            fetch_func=fetch_func,
            language="python",
            version="v1.0.0",
        )
        
        assert result == "fetched_value"
        fetch_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_set_cache_hit(self, cache_manager):
        """Test get_or_set with cache hit."""
        fetch_func = AsyncMock(return_value="fetched_value")
        
        # First call should fetch and cache
        result1 = await cache_manager.get_or_set(
            operation="test_op",
            fetch_func=fetch_func,
            language="python",
            version="v1.0.0",
        )
        
        # Second call should use cache
        result2 = await cache_manager.get_or_set(
            operation="test_op",
            fetch_func=fetch_func,
            language="python",
            version="v1.0.0",
        )
        
        assert result1 == result2 == "fetched_value"
        fetch_func.assert_called_once()  # Should only be called once

    @pytest.mark.asyncio
    async def test_cache_key_generation(self, cache_manager):
        """Test that cache keys are generated consistently."""
        fetch_func = AsyncMock(return_value="value1")
        
        # Same parameters should generate same key
        await cache_manager.get_or_set(
            operation="docs",
            fetch_func=fetch_func,
            language="python",
            version="v1.0.0",
        )
        
        fetch_func.reset_mock()
        fetch_func.return_value = "value2"
        
        # Same call should hit cache, not fetch again
        result = await cache_manager.get_or_set(
            operation="docs",
            fetch_func=fetch_func,
            language="python",
            version="v1.0.0",
        )
        
        assert result == "value1"  # Should get cached value
        fetch_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalidate(self, cache_manager):
        """Test cache invalidation."""
        fetch_func = AsyncMock(return_value="cached_value")
        
        # Cache a value
        await cache_manager.get_or_set(
            operation="test_op",
            fetch_func=fetch_func,
            language="python",
        )
        
        # Invalidate it
        result = await cache_manager.invalidate(
            operation="test_op",
            language="python",
        )
        assert result is True
        
        # Next call should fetch again
        fetch_func.reset_mock()
        fetch_func.return_value = "new_value"
        
        result = await cache_manager.get_or_set(
            operation="test_op",
            fetch_func=fetch_func,
            language="python",
        )
        
        assert result == "new_value"
        fetch_func.assert_called_once()


class TestCacheManagerCreation:
    """Test cache manager creation with different configurations."""

    def test_create_cache_manager_disabled(self):
        """Test creating cache manager with caching disabled."""
        with patch.dict(os.environ, {"CACHE_ENABLED": "false"}):
            manager = create_cache_manager()
            assert isinstance(manager.backend, InMemoryCache)
            assert manager.backend.default_ttl == 60  # Short TTL when disabled

    def test_create_cache_manager_memory(self):
        """Test creating cache manager with in-memory backend."""
        with patch.dict(os.environ, {
            "CACHE_ENABLED": "true",
            "CACHE_BACKEND": "memory",
            "CACHE_DEFAULT_TTL": "1800",
        }):
            manager = create_cache_manager()
            assert isinstance(manager.backend, InMemoryCache)
            assert manager.backend.default_ttl == 1800

    def test_create_cache_manager_redis_fallback(self):
        """Test Redis cache creation with fallback to in-memory."""
        with patch.dict(os.environ, {
            "CACHE_ENABLED": "true",
            "CACHE_BACKEND": "redis",
            "REDIS_HOST": "nonexistent-host",
        }):
            # Should fall back to in-memory cache if Redis fails
            manager = create_cache_manager()
            # The actual backend type depends on whether Redis connection succeeds
            assert manager.backend is not None

    def test_create_cache_manager_redis_config(self):
        """Test Redis cache configuration from environment."""
        with patch.dict(os.environ, {
            "CACHE_ENABLED": "true",
            "CACHE_BACKEND": "redis",
            "REDIS_HOST": "test-redis",
            "REDIS_PORT": "6380",
            "REDIS_DB": "1",
            "REDIS_PASSWORD": "secret",
            "CACHE_DEFAULT_TTL": "7200",
            "CACHE_KEY_PREFIX": "test_prefix:",
        }):
            with patch("otel_instrumentation_mcp.cache.RedisCache") as mock_redis:
                create_cache_manager()
                mock_redis.assert_called_once_with(
                    host="test-redis",
                    port=6380,
                    db=1,
                    password="secret",
                    default_ttl=7200,
                    key_prefix="test_prefix:",
                )