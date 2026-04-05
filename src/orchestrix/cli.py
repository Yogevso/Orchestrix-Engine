"""Orchestrix Admin CLI — manage jobs, workers, and workflows from the terminal."""

import json
import sys

import click
import httpx


DEFAULT_BASE_URL = "http://localhost:8000"


class OrchetrixCLI:
    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.Client(base_url=self.base_url, headers=headers, timeout=30)

    def _print_json(self, data):
        click.echo(json.dumps(data, indent=2, default=str))


pass_cli = click.make_pass_decorator(OrchetrixCLI, ensure=True)


@click.group()
@click.option("--base-url", default=DEFAULT_BASE_URL, envvar="ORCHESTRIX_URL", help="API base URL")
@click.option("--token", default=None, envvar="ORCHESTRIX_TOKEN", help="JWT token for auth")
@click.pass_context
def cli(ctx, base_url: str, token: str | None):
    """Orchestrix Engine — Admin CLI"""
    ctx.obj = OrchetrixCLI(base_url, token)


# ── Health ──


@cli.command()
@click.pass_obj
def health(obj: OrchetrixCLI):
    """Check API health."""
    resp = obj.client.get("/health")
    obj._print_json(resp.json())


# ── Jobs ──


@cli.group()
def jobs():
    """Manage jobs."""
    pass


@jobs.command("list")
@click.option("--status", default=None, help="Filter by status (QUEUED, RUNNING, SUCCEEDED, etc.)")
@click.option("--queue", default=None, help="Filter by queue name")
@click.option("--type", "job_type", default=None, help="Filter by job type")
@click.option("--limit", default=20, help="Max results")
@click.pass_obj
def list_jobs(obj: OrchetrixCLI, status, queue, job_type, limit):
    """List jobs."""
    params = {"limit": limit}
    if status:
        params["status"] = status
    if queue:
        params["queue_name"] = queue
    if job_type:
        params["type"] = job_type
    resp = obj.client.get("/jobs", params=params)
    data = resp.json()
    if data.get("jobs"):
        for j in data["jobs"]:
            click.echo(f"  {j['id'][:8]}  {j['status']:12s}  {j['type']:20s}  q={j['queue_name']}  attempts={j['attempts']}/{j['max_attempts']}")
    click.echo(f"\nTotal: {data.get('total', 0)}")


@jobs.command("get")
@click.argument("job_id")
@click.pass_obj
def get_job(obj: OrchetrixCLI, job_id):
    """Get job details."""
    resp = obj.client.get(f"/jobs/{job_id}")
    if resp.status_code == 404:
        click.echo("Job not found", err=True)
        sys.exit(1)
    obj._print_json(resp.json())


@jobs.command("create")
@click.option("--type", "job_type", required=True, help="Job type")
@click.option("--queue", default="default", help="Queue name")
@click.option("--priority", default=0, type=int, help="Priority (higher = first)")
@click.option("--payload", default="{}", help="JSON payload")
@click.pass_obj
def create_job(obj: OrchetrixCLI, job_type, queue, priority, payload):
    """Create a new job."""
    resp = obj.client.post("/jobs", json={
        "type": job_type,
        "queue_name": queue,
        "priority": priority,
        "payload": json.loads(payload),
    })
    data = resp.json()
    click.echo(f"Created job {data['id']} (status={data['status']})")


@jobs.command("cancel")
@click.argument("job_id")
@click.pass_obj
def cancel_job(obj: OrchetrixCLI, job_id):
    """Cancel a queued/leased job."""
    resp = obj.client.post(f"/jobs/{job_id}/cancel")
    if resp.status_code == 409:
        click.echo("Cannot cancel job in its current state", err=True)
        sys.exit(1)
    click.echo(f"Cancelled job {job_id}")


@jobs.command("requeue")
@click.argument("job_id")
@click.pass_obj
def requeue_job(obj: OrchetrixCLI, job_id):
    """Requeue a dead-lettered job."""
    resp = obj.client.post(f"/jobs/{job_id}/requeue")
    if resp.status_code == 409:
        click.echo("Cannot requeue job in its current state", err=True)
        sys.exit(1)
    click.echo(f"Requeued job {job_id}")


@jobs.command("events")
@click.argument("job_id")
@click.pass_obj
def job_events(obj: OrchetrixCLI, job_id):
    """Show event log for a job."""
    resp = obj.client.get(f"/jobs/{job_id}/events")
    for e in resp.json():
        click.echo(f"  {e['created_at']}  {e['event_type']:15s}  {e.get('message', '')}")


@jobs.command("stats")
@click.pass_obj
def job_stats(obj: OrchetrixCLI):
    """Show queue statistics."""
    resp = obj.client.get("/jobs/stats")
    for s in resp.json():
        click.echo(
            f"  {s['queue_name']:15s}  "
            f"queued={s['queued']}  running={s['running']}  "
            f"succeeded={s['succeeded']}  failed={s['failed']}  dead={s['dead_letter']}"
        )


# ── Workers ──


@cli.group()
def workers():
    """Manage workers."""
    pass


@workers.command("list")
@click.pass_obj
def list_workers(obj: OrchetrixCLI):
    """List registered workers."""
    resp = obj.client.get("/workers")
    for w in resp.json():
        click.echo(
            f"  {w['id'][:8]}  {w['name']:15s}  status={w['status']}  "
            f"queues={','.join(w['queues'])}  concurrency={w['max_concurrency']}"
        )


# ── Workflows ──


@cli.group()
def workflows():
    """Manage workflows."""
    pass


@workflows.command("list")
@click.pass_obj
def list_workflows(obj: OrchetrixCLI):
    """List workflow definitions."""
    resp = obj.client.get("/workflows")
    for w in resp.json():
        desc = w.get("description") or ""
        click.echo(f"  {w['id'][:8]}  {w['name']:25s}  {desc[:40]}")


@workflows.command("runs")
@click.option("--workflow-id", default=None, help="Filter by workflow ID")
@click.option("--status", default=None, help="Filter by status")
@click.pass_obj
def list_runs(obj: OrchetrixCLI, workflow_id, status):
    """List workflow runs."""
    params = {}
    if workflow_id:
        params["workflow_id"] = workflow_id
    if status:
        params["status"] = status
    resp = obj.client.get("/workflows/runs", params=params)
    for r in resp.json():
        click.echo(
            f"  {r['id'][:8]}  wf={r['workflow_id'][:8]}  "
            f"status={r['status']}  steps={len(r.get('steps', []))}"
        )


@workflows.command("run")
@click.argument("workflow_id")
@click.option("--payload", default="{}", help="JSON input payload")
@click.pass_obj
def start_run(obj: OrchetrixCLI, workflow_id, payload):
    """Start a new workflow run."""
    resp = obj.client.post("/workflows/runs", json={
        "workflow_id": workflow_id,
        "input_payload": json.loads(payload),
    })
    data = resp.json()
    click.echo(f"Started run {data['id']} (status={data['status']}, steps={len(data.get('steps', []))})")


@workflows.command("pause")
@click.argument("run_id")
@click.pass_obj
def pause_run(obj: OrchetrixCLI, run_id):
    """Pause a running workflow run."""
    resp = obj.client.post(f"/workflows/runs/{run_id}/pause")
    if resp.status_code == 409:
        click.echo("Cannot pause this run", err=True)
        sys.exit(1)
    click.echo(f"Paused run {run_id}")


@workflows.command("resume")
@click.argument("run_id")
@click.pass_obj
def resume_run(obj: OrchetrixCLI, run_id):
    """Resume a paused workflow run."""
    resp = obj.client.post(f"/workflows/runs/{run_id}/resume")
    if resp.status_code == 409:
        click.echo("Cannot resume this run", err=True)
        sys.exit(1)
    click.echo(f"Resumed run {run_id}")


# ── Recurring ──


@cli.group()
def recurring():
    """Manage recurring jobs."""
    pass


@recurring.command("list")
@click.pass_obj
def list_recurring(obj: OrchetrixCLI):
    """List recurring job definitions."""
    resp = obj.client.get("/recurring")
    for r in resp.json():
        enabled = "ON" if r["enabled"] else "OFF"
        click.echo(
            f"  {r['id'][:8]}  {r['name']:20s}  {r['cron_expression']:15s}  "
            f"{enabled}  type={r['type']}  queue={r['queue_name']}"
        )


@recurring.command("create")
@click.option("--name", required=True, help="Recurring job name")
@click.option("--type", "job_type", required=True, help="Job type")
@click.option("--cron", required=True, help="Cron expression (5-field)")
@click.option("--queue", default="default", help="Queue name")
@click.option("--payload", default="{}", help="JSON payload")
@click.pass_obj
def create_recurring(obj: OrchetrixCLI, name, job_type, cron, queue, payload):
    """Create a recurring job."""
    resp = obj.client.post("/recurring", json={
        "name": name,
        "type": job_type,
        "cron_expression": cron,
        "queue_name": queue,
        "payload": json.loads(payload),
    })
    data = resp.json()
    click.echo(f"Created recurring job {data['id']} (next_run={data.get('next_run_at')})")


# ── Metrics ──


@cli.command()
@click.pass_obj
def metrics(obj: OrchetrixCLI):
    """Show Prometheus metrics."""
    resp = obj.client.get("/metrics")
    click.echo(resp.text)


# ── Entry point ──

def main():
    cli()


if __name__ == "__main__":
    main()
