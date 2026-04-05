#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# Orchestrix Engine — Live Demo Script
# Run: bash scripts/demo.sh
# Requires: curl, jq, docker compose running
# ──────────────────────────────────────────────────────────────────

set -euo pipefail
API="http://localhost:8000"
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

step() { echo -e "\n${BOLD}${CYAN}═══ $1 ═══${NC}\n"; }
info() { echo -e "${GREEN}→${NC} $1"; }
warn() { echo -e "${YELLOW}→${NC} $1"; }
wait_for() { sleep "${1:-2}"; }

# ── 1. Health Check ──────────────────────────────────────────────
step "1/7  Health Check"
curl -s "$API/health" | jq .
info "API is alive"

# ── 2. Check Workers ────────────────────────────────────────────
step "2/7  Active Workers"
curl -s "$API/workers" | jq '[.[] | {name, status, queues}]'
info "Workers registered and polling for jobs"

# ── 3. Normal Job Execution ─────────────────────────────────────
step "3/7  Normal Job Execution"
info "Creating email.send job..."
JOB=$(curl -s -X POST "$API/jobs" \
  -H "Content-Type: application/json" \
  -d '{"type":"email.send","queue":"default","payload":{"to":"demo@orchestrix.io","subject":"Hello from Orchestrix"}}')
JOB_ID=$(echo "$JOB" | jq -r '.id')
echo "$JOB" | jq '{id: .id, type: .type, status: .status}'
info "Job $JOB_ID created → waiting for worker to process..."
wait_for 3
STATUS=$(curl -s "$API/jobs/$JOB_ID" | jq -r '.status')
info "Job status: $STATUS ✓"

# ── 4. Retry & Dead-Letter ──────────────────────────────────────
step "4/7  Retry Policies & Dead-Letter Queue"
info "Creating chaos.fail job (max 3 attempts)..."
CHAOS=$(curl -s -X POST "$API/jobs" \
  -H "Content-Type: application/json" \
  -d '{"type":"chaos.fail","queue":"default","payload":{"reason":"demo: testing retries"},"max_attempts":3}')
CHAOS_ID=$(echo "$CHAOS" | jq -r '.id')
echo "$CHAOS" | jq '{id: .id, type: .type, status: .status, max_attempts: .max_attempts}'
info "Waiting for 3 retry attempts..."
wait_for 10
CHAOS_FINAL=$(curl -s "$API/jobs/$CHAOS_ID")
echo "$CHAOS_FINAL" | jq '{status: .status, attempts: .attempts, last_error: .last_error}'
info "Job exhausted all retries → moved to DEAD_LETTER"

info "Viewing event timeline..."
curl -s "$API/jobs/$CHAOS_ID/events" | jq '[.[] | {event_type, message, created_at}]'

# ── 5. Queue Stats ──────────────────────────────────────────────
step "5/7  Queue Statistics"
curl -s "$API/jobs/stats" | jq .
info "Live queue depth breakdown"

# ── 6. Workflow DAG Execution ───────────────────────────────────
step "6/7  Workflow DAG: Fan-out → Fan-in"
info "Creating ETL pipeline workflow (extract → transform + validate → load)..."
WF=$(curl -s -X POST "$API/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "demo-etl-pipeline",
    "description": "Extract → parallel transform+validate → load",
    "steps": [
      {"name": "extract", "job_type": "data.process", "payload": {"source": "s3://demo/input"}},
      {"name": "transform", "job_type": "data.process", "depends_on": ["extract"], "payload": {"op": "transform"}},
      {"name": "validate", "job_type": "data.process", "depends_on": ["extract"], "payload": {"op": "validate"}},
      {"name": "load", "job_type": "data.process", "depends_on": ["transform", "validate"], "payload": {"dest": "warehouse"}}
    ]
  }')
WF_ID=$(echo "$WF" | jq -r '.id')
echo "$WF" | jq '{id: .id, name: .name, steps: (.steps | length)}'

info "Starting workflow run..."
RUN=$(curl -s -X POST "$API/workflows/runs" \
  -H "Content-Type: application/json" \
  -d "{\"workflow_id\": \"$WF_ID\"}")
RUN_ID=$(echo "$RUN" | jq -r '.id')
echo "$RUN" | jq '{run_id: .id, status: .status, steps: [.steps[] | {name: .step_name, status}]}'

info "Waiting for DAG to execute (extract → fan-out → fan-in → load)..."
wait_for 15
RUN_FINAL=$(curl -s "$API/workflows/runs/$RUN_ID")
echo "$RUN_FINAL" | jq '{status: .status, steps: [.steps[] | {name: .step_name, status}]}'
info "Workflow completed with fan-out/fan-in ✓"

# ── 7. Requeue Dead-Lettered Job ────────────────────────────────
step "7/7  Manual Recovery: Requeue Dead-Lettered Job"
info "Requeuing the failed chaos job..."
REQUEUED=$(curl -s -X POST "$API/jobs/$CHAOS_ID/requeue")
echo "$REQUEUED" | jq '{id: .id, status: .status, attempts: .attempts}'
info "Job back in queue for another chance ✓"

# ── Summary ─────────────────────────────────────────────────────
step "Demo Complete"
echo -e "${GREEN}✓${NC} Job execution with lease-based ownership"
echo -e "${GREEN}✓${NC} Retry policies with exponential backoff"
echo -e "${GREEN}✓${NC} Dead-letter queue and manual requeue"
echo -e "${GREEN}✓${NC} Full event audit trail"
echo -e "${GREEN}✓${NC} DAG workflow with fan-out / fan-in"
echo -e "${GREEN}✓${NC} Real-time queue statistics"
echo -e ""
echo -e "${BOLD}Dashboard:${NC}  http://localhost:5173"
echo -e "${BOLD}Swagger:${NC}   http://localhost:8000/docs"
echo -e "${BOLD}Metrics:${NC}   http://localhost:8000/metrics"
echo -e "${BOLD}WebSocket:${NC} ws://localhost:8000/ws"
