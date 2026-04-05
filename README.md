# Orchestrix Engine

![CI](https://github.com/Yogevso/Orchestrix-Engine/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

**The execution plane of the [Orchestrix Platform](https://github.com/Yogevso/Orchestrix-Platform).** Owns job scheduling, DAG workflow orchestration, and worker coordination. Consumes JWTs from IAM for tenant-scoped auth. Emits job lifecycle events, queue stats, Prometheus metrics, and real-time WebSocket updates consumed by Console and AI.

Distributed async job & workflow engine with reliable processing, configurable retry policies, recurring jobs, DAG workflows with pause/resume, worker pools, OpenTelemetry tracing, an Admin CLI, and a real-time dashboard.

## Part of the Orchestrix Platform

Orchestrix Engine is the **execution plane** of the Orchestrix Platform — it owns job scheduling, workflow orchestration, and worker coordination.

| Service | Role | Interaction |
|---------|------|-------------|
| **[Orchestrix Console](https://github.com/Yogevso/orchestrix-console)** | Operator UI | Consumes Engine REST API and WebSocket for real-time job/workflow management |
| **[Orchestrix AI](https://github.com/Yogevso/orchestrix-ai)** | Analysis plane | Polls Engine events to detect failures, anomalies, and generate root-cause analysis |
| **[System Insights API](https://github.com/Yogevso/system-insights-api)** | Telemetry backend | Provides host/service metrics that AI correlates with Engine execution data |
| **[Identity Access Service](https://github.com/Yogevso/identity-access-service)** | Shared auth | Issues JWTs that Engine validates for tenant-scoped, role-based access control |

**Data Engine exposes:**
- Job lifecycle events (`QUEUED → RUNNING → SUCCEEDED/FAILED → DEAD_LETTER`)
- Workflow run state transitions and step completions
- Worker health via heartbeats and registration
- Queue statistics and Prometheus metrics
- Real-time push via WebSocket (`job.update`, `workflow.update`, `worker.update`)

### Platform Architecture

```mermaid
flowchart TB
    Console["Orchestrix Console\n:5173 — Operator UI"]
    Engine["Orchestrix Engine\n:8000 — Execution Plane"]
    AI["Orchestrix AI\n:8001 — Analysis Plane"]
    Insights["System Insights API\n:8002 — Telemetry Backend"]
    IAM["Identity Access Service\n:8003 — Auth & RBAC"]

    Console -- "/api — jobs, workflows, workers" --> Engine
    Console -- "/ai — incident analysis" --> AI
    Console -- "/insights — host metrics" --> Insights
    Console -- "/iam — login, tokens" --> IAM

    AI -- "poll events & jobs" --> Engine
    AI -- "correlate host metrics" --> Insights
    Engine -. "validate JWT" .-> IAM
    AI -. "validate JWT" .-> IAM

    style Engine fill:#7c3aed,color:#fff,stroke:#7c3aed
```

## What Is This?

Orchestrix Engine is a production-style execution platform designed to reliably run background jobs and multi-step workflows under real-world failure conditions — worker crashes, retries, timeouts, and system overload. It implements the same patterns used by systems like Celery, Temporal, and AWS Step Functions, built from scratch to demonstrate deep understanding of distributed systems.

## Why This Exists

Most backend systems rely on background jobs, but handling failures, retries, and distributed workers correctly is hard. Simple task queues break down when workers crash mid-execution, when jobs need to be retried with backoff, or when multi-step workflows require coordination across services.

This project was built to explore how real production systems ensure reliable execution under failure, and to implement production-grade patterns such as lease-based ownership, heartbeat monitoring, dead-letter recovery, DAG orchestration, and distributed worker coordination — all from first principles.

## Architecture

```
┌──────────┐     ┌──────────────┐     ┌─────────────┐
│  Client   │────▶│   API Service │────▶│  PostgreSQL  │
│  / CLI    │◀──ws│  (FastAPI)    │     └──────┬──────┘
└──────────┘     └──────┬───────┘            │
                        │              ┌──────▼──────┐
                 ┌──────▼───────┐      │   Workers    │
                 │  Scheduler    │      │  (poll,      │
                 │  (recovery,   │      │   execute,   │
                 │   cron,       │      │   heartbeat) │
                 │   workflows)  │      └─────────────┘
                 └──────────────┘
                        │
                 ┌──────▼───────┐      ┌─────────────┐
                 │  Dashboard    │      │  OTel / Jaeger│
                 │  (React UI)   │      │  (tracing)   │
                 └──────────────┘      └─────────────┘
```

**Services:**
- **API** — FastAPI with JWT auth, WebSocket live updates, RBAC
- **Workers** — Separate processes that poll, execute, and heartbeat
- **Scheduler** — Recovers stuck jobs, fires cron jobs, advances workflow DAGs
- **Dashboard** — React + Vite UI for real-time monitoring
- **Admin CLI** — `orchestrix` command for managing jobs, workflows, and workers from the terminal

## Job Lifecycle

```
QUEUED → LEASED → RUNNING → SUCCEEDED
                     ↓
                  FAILED → (retry: fixed / linear / exponential) → QUEUED
                              ↓
                         DEAD_LETTER
```

## Workflow DAG Execution

```
PENDING → RUNNING ⇄ PAUSED
              ↓
  step dependencies resolve → fan-out → fan-in → SUCCEEDED
                                                    ↓
                                                 FAILED
```

Steps define dependencies via `depends_on`. The engine dispatches ready steps as jobs, collects results from parent steps (fan-in), and advances the DAG until all leaf steps complete.

## Key Features

### Phase 1 — Core
- **Lease-based ownership** — Workers get time-limited leases, not permanent locks
- **Heartbeats** — Missed heartbeats trigger automatic requeue
- **Configurable retry policies** — Fixed, linear, or exponential backoff per job type
- **Dead-letter queue** — Failed jobs preserved for inspection and replay
- **Stuck-job recovery** — Scheduler detects and requeues crashed worker jobs
- **Event timeline** — Full audit trail per job
- **Idempotency keys** — Prevent duplicate submissions
- **Chaos handlers** — Built-in failure simulation (`chaos.fail`, `chaos.slow`, `chaos.random`)

### Phase 2 — Operations
- **Recurring jobs** — Cron-based schedules with enable/disable toggle
- **Worker capabilities** — Workers declare capabilities for selective dispatch
- **Queue concurrency limits** — Per-queue max concurrency enforcement
- **Multi-tenant support** — `tenant_id` on jobs, workflows, and recurring jobs
- **Job priorities & weighted scheduling** — Priority bands (critical/high/normal/low) with weighted fair scheduling to prevent starvation

### Phase 3 — Workflows & Observability
- **DAG workflows** — Multi-step pipelines with dependency resolution
- **Fan-out / fan-in** — Parallel branches merge parent results automatically
- **Workflow pause / resume** — Pause running workflows and resume them later
- **Step-level retries** — Retry individual failed steps without restarting the run
- **Prometheus metrics** — `/metrics` endpoint for job counts, queue depths, worker status
- **React dashboard** — Real-time views for jobs, workers, and workflow runs

### Phase 4 — Platform
- **JWT authentication & RBAC** — Bearer token auth with admin/operator/viewer roles, per-tenant authorization (disabled by default)
- **WebSocket live updates** — Real-time push notifications for job, workflow, and worker status changes via `/ws`
- **OpenTelemetry tracing** — Distributed tracing with OTLP export, auto-instrumented FastAPI + SQLAlchemy
- **Admin CLI** — `orchestrix` click-based CLI for managing jobs, workers, workflows, and recurring jobs from the terminal
- **CI/CD pipeline** — GitHub Actions: lint (Ruff), test (pytest + Postgres + Redis), Docker build & push to GHCR
- **Full test suite** — pytest-asyncio unit & integration tests with in-memory SQLite

## Live Demo

> All output below is from a real running instance — no mocks.

### 1. Submit a Job → Worker Picks It Up → Succeeds

```bash
$ curl -s -X POST http://localhost:8000/jobs \
    -H "Content-Type: application/json" \
    -d '{"type":"email.send","payload":{"to":"user@example.com","subject":"Welcome"}}'

{
  "id": "daed7004-...",
  "type": "email.send",
  "status": "QUEUED",
  "attempts": 0,
  "max_attempts": 3
}

# A few seconds later...
$ curl -s http://localhost:8000/jobs/daed7004-...

{
  "status": "SUCCEEDED",
  "attempts": 1,
  "payload": {"to": "user@example.com", "subject": "Welcome"}
}
```

### 2. Retry Exhaustion → Dead-Letter → Requeue

```bash
$ curl -s -X POST http://localhost:8000/jobs \
    -H "Content-Type: application/json" \
    -d '{"type":"chaos.fail","payload":{"reason":"testing retries"},"max_attempts":3}'

{
  "id": "344ece6c-...",
  "type": "chaos.fail",
  "status": "QUEUED"
}

# After 3 failed attempts with exponential backoff...
$ curl -s http://localhost:8000/jobs/344ece6c-...

{
  "status": "DEAD_LETTER",
  "attempts": 3,
  "last_error": "Chaos failure: testing retries"
}

# Full event timeline:
$ curl -s http://localhost:8000/jobs/344ece6c-.../events

CREATED → LEASED → RUNNING → RETRIED → LEASED → RUNNING → RETRIED → LEASED → RUNNING → DEAD_LETTERED

# Requeue from dead-letter:
$ curl -s -X POST http://localhost:8000/jobs/344ece6c-.../requeue

{
  "status": "QUEUED",
  "attempts": 0
}
```

### 3. DAG Workflow — Fan-out / Fan-in

```bash
# Define a 4-step ETL pipeline:
#   extract → transform (parallel)
#                        ↘ load
#   extract → validate  (parallel)
#                        ↗

$ curl -s -X POST http://localhost:8000/workflows \
    -H "Content-Type: application/json" \
    -d '{
      "name": "etl-pipeline-demo",
      "steps": [
        {"name": "extract",   "job_type": "data.process", "payload": {"source": "s3://bucket/raw"}},
        {"name": "transform", "job_type": "data.process", "depends_on": ["extract"]},
        {"name": "validate",  "job_type": "data.process", "depends_on": ["extract"]},
        {"name": "load",      "job_type": "data.process", "depends_on": ["transform", "validate"]}
      ]
    }'

# Start the run:
$ curl -s -X POST http://localhost:8000/workflows/runs \
    -d '{"workflow_id": "<workflow-id>"}'

{
  "id": "cb160aa6-...",
  "status": "RUNNING",
  "steps": [
    {"step_name": "extract",   "status": "QUEUED"},
    {"step_name": "transform", "status": "PENDING"},
    {"step_name": "validate",  "status": "PENDING"},
    {"step_name": "load",      "status": "PENDING"}
  ]
}

# Workers execute the DAG: extract → transform+validate (fan-out) → load (fan-in)
$ curl -s http://localhost:8000/workflows/runs/cb160aa6-...

{
  "status": "SUCCEEDED",
  "steps": [
    {"step_name": "extract",   "status": "SUCCEEDED"},
    {"step_name": "transform", "status": "SUCCEEDED"},
    {"step_name": "validate",  "status": "SUCCEEDED"},
    {"step_name": "load",      "status": "SUCCEEDED"}
  ]
}
```

### 4. Queue Statistics

```bash
$ curl -s http://localhost:8000/jobs/stats

[
  {
    "queue_name": "default",
    "queued": 0,
    "leased": 0,
    "running": 0,
    "succeeded": 25,
    "failed": 0,
    "dead_letter": 8
  }
]
```

## Run It Locally

Spin up a full distributed execution environment (API, 2 workers, scheduler, dashboard, Postgres, Redis) with a single command:

```bash
# Start everything (API, 2 workers, scheduler, dashboard, Postgres, Redis)
docker compose up --build

# API:       http://localhost:8000
# Swagger:   http://localhost:8000/docs
# Dashboard: http://localhost:5173
# Metrics:   http://localhost:8000/metrics
# WebSocket: ws://localhost:8000/ws
```

### Admin CLI

```bash
pip install -e .

orchestrix health
orchestrix jobs list --status QUEUED
orchestrix jobs create --type email.send --payload '{"to": "a@b.com"}'
orchestrix jobs stats
orchestrix workers list
orchestrix workflows list
orchestrix workflows run <workflow-id>
orchestrix workflows pause <run-id>
orchestrix workflows resume <run-id>
orchestrix recurring list
orchestrix metrics
```

### Enable Authentication

```bash
# Set environment variables (or add to docker-compose.yml)
export ORCHESTRIX_AUTH_ENABLED=true
export ORCHESTRIX_JWT_SECRET_KEY=your-secure-secret

# Generate a token
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"subject": "admin@orchestrix.io", "role": "admin"}'

# Use the token
curl -H "Authorization: Bearer <token>" http://localhost:8000/auth/me
```

### Run Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## API Reference

### Jobs

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/jobs` | Create a job |
| `GET` | `/jobs` | List jobs (filter: `status`, `queue_name`, `tenant_id`, `worker_id`, `type`) |
| `GET` | `/jobs/stats` | Queue statistics |
| `GET` | `/jobs/{id}` | Get job detail |
| `GET` | `/jobs/{id}/events` | Job event timeline |
| `POST` | `/jobs/{id}/cancel` | Cancel a queued/leased job |
| `POST` | `/jobs/{id}/requeue` | Requeue a dead-lettered/failed job |

### Workers

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/workers` | Register (with capabilities & concurrency) |
| `GET` | `/workers` | List workers |
| `POST` | `/workers/{id}/poll` | Poll for a job |
| `POST` | `/workers/{id}/start` | Start running a leased job |
| `POST` | `/workers/{id}/complete` | Mark job succeeded |
| `POST` | `/workers/{id}/fail` | Mark job failed |
| `POST` | `/workers/{id}/heartbeat` | Send heartbeat |

### Queue Config

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/queues` | List queue configs |
| `PUT` | `/queues/{name}` | Create/update queue config |

### Recurring Jobs

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/recurring` | Create a recurring job |
| `GET` | `/recurring` | List recurring jobs |
| `GET` | `/recurring/{id}` | Get recurring job |
| `PATCH` | `/recurring/{id}` | Enable/disable |
| `DELETE` | `/recurring/{id}` | Delete |

### Workflows

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/workflows` | Create workflow definition |
| `GET` | `/workflows` | List workflows |
| `GET` | `/workflows/{id}` | Get workflow |
| `POST` | `/workflows/runs` | Start a workflow run |
| `GET` | `/workflows/runs` | List runs (filter: `workflow_id`, `status`, `tenant_id`) |
| `GET` | `/workflows/runs/{id}` | Get run with steps |
| `POST` | `/workflows/runs/{id}/cancel` | Cancel a running workflow |
| `POST` | `/workflows/runs/{id}/pause` | Pause a running workflow |
| `POST` | `/workflows/runs/{id}/resume` | Resume a paused workflow |
| `POST` | `/workflows/steps/{id}/retry` | Retry a failed step |

### Auth

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/auth/token` | Generate a JWT token (requires admin) |
| `GET` | `/auth/me` | Get current user info |

### WebSocket

| Protocol | Endpoint | Description |
|----------|----------|-------------|
| `WS` | `/ws` | Live updates (topics: `job.update`, `workflow.update`, `worker.update`) |

### Metrics

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/metrics` | Prometheus-format metrics |

## Examples

### Create & Run a Workflow

```bash
# Define a 3-step pipeline: extract → transform → load
curl -X POST http://localhost:8000/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "name": "etl-pipeline",
    "steps": [
      {"name": "extract", "job_type": "etl.extract", "payload": {"source": "s3://bucket/file"}},
      {"name": "transform", "job_type": "etl.transform", "depends_on": ["extract"]},
      {"name": "load", "job_type": "etl.load", "depends_on": ["transform"]}
    ]
  }'

# Start a run
curl -X POST http://localhost:8000/workflows/runs \
  -H "Content-Type: application/json" \
  -d '{"workflow_id": "<workflow-id>"}'
```

### Fan-out / Fan-in Workflow

```bash
curl -X POST http://localhost:8000/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "name": "map-reduce",
    "steps": [
      {"name": "split", "job_type": "mr.split"},
      {"name": "process-a", "job_type": "mr.process", "depends_on": ["split"]},
      {"name": "process-b", "job_type": "mr.process", "depends_on": ["split"]},
      {"name": "aggregate", "job_type": "mr.aggregate", "depends_on": ["process-a", "process-b"]}
    ]
  }'
```

### Set Up a Recurring Job

```bash
curl -X POST http://localhost:8000/recurring \
  -H "Content-Type: application/json" \
  -d '{
    "name": "cleanup-daily",
    "type": "maintenance.cleanup",
    "cron_expression": "0 3 * * *",
    "queue_name": "maintenance"
  }'
```

### Chaos Testing

```bash
# Retry → dead-letter cycle
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"type": "chaos.fail", "payload": {"reason": "testing"}, "max_attempts": 3}'

# Worker crash simulation
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"type": "chaos.slow", "payload": {"duration": 120}}'
docker compose stop worker-1
# Lease expires → scheduler requeues → worker-2 picks it up
```

## Demo Scenarios

| # | Scenario | What Happens |
|---|----------|--------------|
| 1 | **Normal Execution** | Submit a job → worker picks it up → `SUCCEEDED`. See [Live Demo §1](#1-submit-a-job--worker-picks-it-up--succeeds). |
| 2 | **Worker Crash Recovery** | Submit a slow job → kill the worker → lease expires → scheduler requeues → another worker completes it. Zero data loss. |
| 3 | **Retry & Dead-Letter** | `chaos.fail` handler → exponential backoff retries → `DEAD_LETTER` after max attempts → requeue from API/CLI/dashboard. See [Live Demo §2](#2-retry-exhaustion--dead-letter--requeue). |
| 4 | **DAG Workflow** | Multi-step pipeline with fan-out/fan-in → steps execute in dependency order → pause/resume mid-execution. See [Live Demo §3](#3-dag-workflow--fan-out--fan-in). |
| 5 | **Recurring Jobs** | Cron-scheduled job → scheduler fires on schedule → workers process each occurrence automatically. |

## Tech Stack

- **Backend:** FastAPI, SQLAlchemy (async), PostgreSQL, Pydantic v2
- **Auth:** PyJWT, RBAC roles (admin/operator/viewer), per-tenant isolation
- **Workers:** Python async with heartbeat loops
- **Scheduler:** Cron firing, DAG advancement, stuck-job recovery
- **Real-time:** WebSocket push (topic-based pub/sub)
- **Tracing:** OpenTelemetry SDK, OTLP exporter, FastAPI + SQLAlchemy auto-instrumentation
- **Dashboard:** React 18, Vite, TypeScript, react-router-dom
- **CLI:** Click-based `orchestrix` command
- **Testing:** pytest-asyncio, aiosqlite (in-memory), httpx async client
- **CI/CD:** GitHub Actions (lint, test, Docker build & push)
- **Infra:** Docker Compose, Alembic migrations, Redis (signaling)

## Project Structure

```
src/orchestrix/
├── api/
│   ├── app.py          # FastAPI application + OTel setup
│   ├── auth.py         # Auth routes (/auth/token, /auth/me)
│   ├── jobs.py         # Job + queue config + recurring routes
│   ├── workers.py      # Worker endpoints
│   ├── workflows.py    # Workflow + run + pause/resume endpoints
│   ├── metrics.py      # Prometheus metrics
│   └── ws.py           # WebSocket live updates endpoint
├── engine/
│   ├── core.py         # Job engine, queue config, recurring jobs
│   ├── workflows.py    # DAG workflow engine + pause/resume
│   ├── priority.py     # Weighted fair scheduling & priority bands
│   └── retry.py        # Configurable retry policies (fixed/linear/exponential)
├── models/
│   ├── enums.py        # All status enums
│   └── tables.py       # SQLAlchemy models (7 tables)
├── worker/
│   ├── handlers.py     # Task handler registry
│   └── process.py      # Worker process loop
├── auth.py             # JWT auth, RBAC, role hierarchy
├── cli.py              # Click-based admin CLI
├── config.py           # Settings (env-based, auth, OTel)
├── cron.py             # Cron expression parser
├── database.py         # Async DB session
├── scheduler.py        # Recovery, cron, workflow scheduler
├── telemetry.py        # OpenTelemetry setup & instrumentation
└── websocket.py        # WebSocket connection manager

tests/
├── conftest.py         # Shared fixtures (in-memory SQLite, test client)
├── test_core.py        # Core engine unit tests
├── test_workflows.py   # Workflow engine unit tests
├── test_api.py         # API integration tests
└── test_cron.py        # Cron parser unit tests

dashboard/
├── src/
│   ├── pages/          # Jobs, Workers, Workflows, RunDetail
│   ├── api.ts          # API client
│   ├── App.tsx         # Router layout
│   └── index.css       # Dark theme styles
└── package.json

.github/workflows/ci.yml  # CI/CD: lint, test, Docker build & push
```

## Key Takeaways

- Designed a distributed job execution engine with lease-based task ownership and automatic failure recovery
- Implemented configurable retry policies (fixed, linear, exponential) with dead-letter queues and idempotency guarantees
- Built a workflow DAG engine with dependency resolution, fan-out/fan-in, pause/resume, and step-level retries
- Added JWT authentication with role-based access control (admin/operator/viewer) and per-tenant authorization
- Built WebSocket live updates for real-time push notifications to connected clients
- Integrated OpenTelemetry for distributed tracing across API, workers, and database layers
- Created an admin CLI (`orchestrix`) for managing the entire platform from the terminal
- Set up CI/CD with GitHub Actions: lint, test with real Postgres/Redis, Docker build & publish
- 39 automated tests (unit + integration) with pytest-asyncio and in-memory SQLite
- Engineered for fault tolerance: heartbeat monitoring, stuck-job recovery, and chaos testing built in
