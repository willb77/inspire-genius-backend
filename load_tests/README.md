# Load Testing — Inspire Genius Backend

## Prerequisites

```bash
pip install locust
```

## Running Tests

### Quick Run (100 users)

```bash
locust -f load_tests/locustfile.py --headless -u 100 -r 10 -t 60s
```

### Using Config File

```bash
locust -f load_tests/locustfile.py --config load_tests/locust.conf
```

### With Web UI

```bash
locust -f load_tests/locustfile.py
# Open http://localhost:8089
```

## Test Scenarios

| Scenario | Users | Spawn Rate | Duration | Command |
|----------|-------|------------|----------|---------|
| Normal   | 100   | 10/s       | 60s      | `locust -f load_tests/locustfile.py --headless -u 100 -r 10 -t 60s` |
| Peak     | 500   | 25/s       | 120s     | `locust -f load_tests/locustfile.py --headless -u 500 -r 25 -t 120s` |
| Stress   | 1000  | 50/s       | 180s     | `locust -f load_tests/locustfile.py --headless -u 1000 -r 50 -t 180s` |

## Task Weights

| Task             | Weight | Tag        |
|------------------|--------|------------|
| Dashboard Stats  | 5      | critical   |
| Login            | 3      | auth       |
| Activity Feed    | 3      | dashboard  |
| Submit Feedback  | 2      | feedback   |
| List Feedback    | 2      | feedback   |
| Analytics        | 2      | analytics  |
| Goals            | 2      | goals      |
| Training         | 1      | training   |
| Costs            | 1      | costs      |
| Reports          | 1      | reports    |

## Running by Tag

```bash
# Critical paths only
locust -f load_tests/locustfile.py --tags critical --headless -u 100 -r 10 -t 60s

# Auth flow only
locust -f load_tests/locustfile.py --tags auth --headless -u 50 -r 5 -t 30s
```

## Target SLAs

| Metric | Normal (100u) | Peak (500u) | Stress (1000u) |
|--------|---------------|-------------|----------------|
| p50    | < 100ms       | < 200ms     | < 500ms        |
| p95    | < 500ms       | < 1s        | < 2s           |
| p99    | < 1s          | < 2s        | < 5s           |
| Error  | < 0.1%        | < 1%        | < 5%           |
| RPS    | > 200         | > 500       | > 300          |

## Setup

Before running load tests, ensure:

1. The backend is running: `uvicorn prism_inspire.main:app --reload`
2. A test user exists: `loadtest@example.com` / `TestPass123!`
3. The database is migrated: `alembic upgrade head`
