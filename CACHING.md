# Caching in OpenTelemetry Instrumentation MCP

This document describes the optional caching functionality available in the OpenTelemetry Instrumentation MCP server.

## Overview

The MCP server supports optional caching to improve performance and reduce API calls to external services like GitHub. Caching is **disabled by default** and can be enabled with Redis or in-memory backends.

## Features

- **Optional**: Caching is disabled by default, no impact on existing deployments
- **Pluggable**: Support for in-memory and Redis backends
- **Version-aware**: Different cache TTLs based on content type and version stability
- **Graceful degradation**: Falls back gracefully if cache backend is unavailable
- **Observability**: Cache operations are instrumented with OpenTelemetry traces
- **Health monitoring**: Cache health is included in health check endpoints

## Cache Backends

### In-Memory Cache (Default when enabled)
- Simple in-memory storage with TTL support
- Suitable for single-instance deployments
- Data is lost on pod restart
- No external dependencies

### Redis Cache (Recommended for production)
- Distributed cache shared across multiple pods
- Persistent across pod restarts
- High availability with Redis Cluster
- Requires Redis deployment

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_ENABLED` | `false` | Enable/disable caching |
| `CACHE_BACKEND` | `memory` | Cache backend: `memory` or `redis` |
| `CACHE_DEFAULT_TTL` | `3600` | Default TTL in seconds |
| `CACHE_KEY_PREFIX` | `otel_mcp:` | Prefix for cache keys |
| `REDIS_HOST` | `localhost` | Redis host (Redis backend only) |
| `REDIS_PORT` | `6379` | Redis port (Redis backend only) |
| `REDIS_DB` | `0` | Redis database number (Redis backend only) |
| `REDIS_PASSWORD` | - | Redis password (Redis backend only) |

### Cache TTL Strategy

Different content types have different cache durations:

- **Documentation (stable versions)**: 24 hours
- **Documentation (main/latest)**: 1 hour  
- **Semantic Conventions**: 6 hours
- **GitHub Issues**: 1 hour
- **Repository Lists**: 24 hours

## Deployment Options

### Option 1: No Caching (Default)
```yaml
# No additional configuration needed
# CACHE_ENABLED defaults to false
```

### Option 2: In-Memory Caching
```yaml
env:
  - name: CACHE_ENABLED
    value: "true"
  - name: CACHE_BACKEND
    value: "memory"
  - name: CACHE_DEFAULT_TTL
    value: "3600"
```

### Option 3: Redis Caching
```yaml
env:
  - name: CACHE_ENABLED
    value: "true"
  - name: CACHE_BACKEND
    value: "redis"
  - name: REDIS_HOST
    value: "redis-cache"
  - name: REDIS_PORT
    value: "6379"
```

## Kubernetes Deployment with Redis

### Using the Redis Overlay

Deploy with Redis caching enabled:

```bash
kubectl apply -k manifests/overlays/redis/
```

This deploys:
- MCP server with caching enabled
- Redis deployment with optimized cache configuration
- Service for Redis connectivity

### Manual Redis Deployment

1. **Deploy Redis**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis-cache
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis-cache
  template:
    metadata:
      labels:
        app: redis-cache
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        args:
        - redis-server
        - --maxmemory
        - 256mb
        - --maxmemory-policy
        - allkeys-lru
        ports:
        - containerPort: 6379
---
apiVersion: v1
kind: Service
metadata:
  name: redis-cache
spec:
  selector:
    app: redis-cache
  ports:
  - port: 6379
    targetPort: 6379
```

2. **Update MCP deployment**:
```yaml
env:
- name: CACHE_ENABLED
  value: "true"
- name: CACHE_BACKEND
  value: "redis"
- name: REDIS_HOST
  value: "redis-cache"
```

## Installation

### With Redis Support
```bash
# Install with Redis dependencies
pip install "otel-instrumentation-mcp[redis]"
```

### Without Redis Support
```bash
# Standard installation (in-memory caching only)
pip install otel-instrumentation-mcp
```

## Monitoring

### Health Checks

Cache health is included in the health endpoints:

```bash
# Overall health including cache status
curl http://localhost:8080/health

# Dedicated cache status
curl http://localhost:8080/cache/status
```

Example response:
```json
{
  "cache": {
    "status": "healthy",
    "backend": "redis",
    "host": "redis-cache",
    "port": 6379,
    "connected_clients": 2,
    "used_memory_human": "1.2M",
    "redis_version": "7.2.0"
  },
  "cache_enabled": true,
  "cache_backend": "redis"
}
```

### OpenTelemetry Traces

All cache operations are instrumented with OpenTelemetry:

- Cache hits/misses are recorded as span events
- Cache operation duration is tracked
- Cache backend health is monitored
- Errors are captured with full context

Example trace attributes:
```
cache.operation: "docs_by_language"
cache.key: "docs_by_language:lang:python:ver:v1.2.3"
cache.backend: "RedisCache"
cache.hit: true
```

## Performance Impact

### With Caching Enabled
- **Cache Hit**: ~1-5ms response time
- **Cache Miss**: Normal API response time + ~5-10ms caching overhead
- **Memory Usage**: Minimal for in-memory, none for Redis
- **Network**: Reduced external API calls

### Cache Hit Rates (Expected)
- **Documentation**: 80-90% (stable content)
- **Semantic Conventions**: 90-95% (infrequent changes)
- **GitHub Issues**: 60-70% (more dynamic content)

## Best Practices

### Production Deployments
1. **Use Redis** for multi-replica deployments
2. **Monitor cache health** via health endpoints
3. **Set appropriate TTLs** based on content freshness requirements
4. **Use Redis Cluster** for high availability
5. **Monitor cache hit rates** via OpenTelemetry metrics

### Development/Testing
1. **Disable caching** for development (default)
2. **Use in-memory cache** for integration tests
3. **Test cache invalidation** scenarios
4. **Verify graceful degradation** when cache is unavailable

### Security Considerations
1. **Use Redis AUTH** in production environments
2. **Network isolation** for Redis deployment
3. **Regular security updates** for Redis image
4. **Monitor Redis logs** for suspicious activity

## Troubleshooting

### Common Issues

**Cache not working**:
- Verify `CACHE_ENABLED=true`
- Check cache backend configuration
- Review health endpoint for errors

**Redis connection failures**:
- Verify Redis service is running
- Check network connectivity
- Validate Redis host/port configuration
- Review Redis logs for errors

**High memory usage**:
- Adjust Redis `maxmemory` setting
- Review cache TTL values
- Monitor cache hit rates
- Consider cache key patterns

### Debug Commands

```bash
# Check cache status
curl http://localhost:8080/cache/status

# Check overall health
curl http://localhost:8080/health

# Redis CLI (if Redis is accessible)
redis-cli -h redis-cache ping
redis-cli -h redis-cache info memory
redis-cli -h redis-cache keys "otel_mcp:*"
```

## Migration Guide

### Enabling Caching on Existing Deployment

1. **Update environment variables**:
```yaml
env:
- name: CACHE_ENABLED
  value: "true"
```

2. **Deploy Redis** (optional but recommended):
```bash
kubectl apply -f redis-deployment.yaml
```

3. **Update MCP configuration**:
```yaml
env:
- name: CACHE_BACKEND
  value: "redis"
- name: REDIS_HOST
  value: "redis-cache"
```

4. **Restart MCP pods**:
```bash
kubectl rollout restart deployment/otel-instrumentation-mcp
```

### Disabling Caching

1. **Set environment variable**:
```yaml
env:
- name: CACHE_ENABLED
  value: "false"
```

2. **Restart pods**:
```bash
kubectl rollout restart deployment/otel-instrumentation-mcp
```

3. **Remove Redis** (optional):
```bash
kubectl delete deployment redis-cache
kubectl delete service redis-cache
```

## Future Enhancements

- **Cache warming**: Pre-populate cache with frequently accessed data
- **Cache analytics**: Detailed metrics on cache performance
- **Multi-level caching**: L1 (memory) + L2 (Redis) caching
- **Cache invalidation API**: Manual cache invalidation endpoints
- **Distributed cache invalidation**: Coordinate cache updates across pods