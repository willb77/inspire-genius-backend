# Performance SLAs — Inspire Genius Backend

## Response Time Targets

| Operation Type | p50 | p95 | p99 | Max |
|---|---|---|---|---|
| Read (GET) | < 100ms | < 500ms | < 1s | 2s |
| Write (POST/PUT/PATCH) | < 200ms | < 1s | < 2s | 5s |
| Analytics/Aggregation | < 500ms | < 2s | < 5s | 10s |
| File Export | < 1s | < 5s | < 10s | 30s |

## Throughput Targets

| Scenario | Concurrent Users | Requests/sec | Error Rate |
|---|---|---|---|
| Normal | 100 | > 200 | < 0.1% |
| Peak | 500 | > 500 | < 1% |
| Stress | 1000 | > 300 | < 5% |

## Query Performance

- All database queries: < 100ms p95
- N+1 patterns: eliminated via eager loading
- Pagination: enforced on all list endpoints (max 100 per page)

## Connection Pool

- Pool size: 50 connections
- Max overflow: 100
- Pool timeout: 30s
- Connection recycle: 1800s (30 min)

## Circuit Breaker

- Failure threshold: 5 consecutive failures
- Reset timeout: 60s
- Monitored services: Cognito, S3, Milvus, LLM providers

## Memory

- Warning threshold: 512 MB
- Maximum: 1 GB (container limit)

## Timeouts

- Default request: 30s
- Long operations (export, reports): 120s
- WebSocket idle: 300s
