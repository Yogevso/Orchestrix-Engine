"""Integration tests for the FastAPI API endpoints."""

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


# ── Health ──


async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Jobs CRUD ──


async def test_create_and_get_job(client: AsyncClient):
    resp = await client.post("/jobs", json={"type": "email.send", "payload": {"to": "x@y.com"}})
    assert resp.status_code == 201
    data = resp.json()
    assert data["type"] == "email.send"
    assert data["status"] == "QUEUED"

    # Get by ID
    job_id = data["id"]
    resp2 = await client.get(f"/jobs/{job_id}")
    assert resp2.status_code == 200
    assert resp2.json()["id"] == job_id


async def test_list_jobs(client: AsyncClient):
    await client.post("/jobs", json={"type": "email.send", "payload": {}})
    resp = await client.get("/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["jobs"]) >= 1


async def test_get_job_events(client: AsyncClient):
    resp = await client.post("/jobs", json={"type": "email.send", "payload": {}})
    job_id = resp.json()["id"]
    resp2 = await client.get(f"/jobs/{job_id}/events")
    assert resp2.status_code == 200
    events = resp2.json()
    assert len(events) >= 1
    assert events[0]["event_type"] == "CREATED"


async def test_cancel_job(client: AsyncClient):
    resp = await client.post("/jobs", json={"type": "email.send", "payload": {}})
    job_id = resp.json()["id"]
    resp2 = await client.post(f"/jobs/{job_id}/cancel")
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "CANCELLED"


async def test_job_stats(client: AsyncClient):
    await client.post("/jobs", json={"type": "data.process", "payload": {}, "queue_name": "test-stats"})
    resp = await client.get("/jobs/stats")
    assert resp.status_code == 200


# ── Workers ──


async def test_register_and_list_workers(client: AsyncClient):
    resp = await client.post("/workers", json={"name": "api-w1", "queues": ["default"]})
    assert resp.status_code == 201
    assert resp.json()["name"] == "api-w1"

    resp2 = await client.get("/workers")
    assert resp2.status_code == 200
    names = [w["name"] for w in resp2.json()]
    assert "api-w1" in names


# ── Workflows ──


async def test_workflow_lifecycle(client: AsyncClient):
    # Create workflow
    resp = await client.post("/workflows", json={
        "name": "api-test-wf",
        "description": "Test",
        "steps": [
            {"name": "s1", "job_type": "email.send", "payload": {}, "depends_on": []},
            {"name": "s2", "job_type": "data.process", "payload": {}, "depends_on": ["s1"]},
        ],
    })
    assert resp.status_code == 201
    wf_id = resp.json()["id"]

    # List workflows
    resp2 = await client.get("/workflows")
    assert resp2.status_code == 200

    # Start a run
    resp3 = await client.post("/workflows/runs", json={"workflow_id": wf_id, "input_payload": {}})
    assert resp3.status_code == 201
    run_id = resp3.json()["id"]
    assert resp3.json()["status"] == "RUNNING"

    # Get run detail
    resp4 = await client.get(f"/workflows/runs/{run_id}")
    assert resp4.status_code == 200
    assert len(resp4.json()["steps"]) == 2


async def test_workflow_cycle_rejected(client: AsyncClient):
    resp = await client.post("/workflows", json={
        "name": "cyclic-api-wf",
        "steps": [
            {"name": "a", "job_type": "x", "payload": {}, "depends_on": ["b"]},
            {"name": "b", "job_type": "x", "payload": {}, "depends_on": ["a"]},
        ],
    })
    assert resp.status_code == 422


# ── Queues ──


async def test_queue_config(client: AsyncClient):
    resp = await client.put("/queues/test-q", json={"queue_name": "test-q", "max_concurrency": 5})
    assert resp.status_code == 200
    assert resp.json()["max_concurrency"] == 5

    resp2 = await client.get("/queues")
    assert resp2.status_code == 200


# ── Recurring Jobs ──


async def test_recurring_job_crud(client: AsyncClient):
    resp = await client.post("/recurring", json={
        "name": "daily-report",
        "type": "report.generate",
        "cron_expression": "0 9 * * *",
    })
    assert resp.status_code == 201
    rj_id = resp.json()["id"]

    resp2 = await client.get("/recurring")
    assert resp2.status_code == 200
    assert any(r["id"] == rj_id for r in resp2.json())

    # Toggle
    resp3 = await client.patch(f"/recurring/{rj_id}", json={"enabled": False})
    assert resp3.status_code == 200
    assert resp3.json()["enabled"] is False

    # Delete
    resp4 = await client.delete(f"/recurring/{rj_id}")
    assert resp4.status_code == 204


# ── Metrics ──


async def test_metrics_endpoint(client: AsyncClient):
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "orchestrix_jobs_total" in resp.text
