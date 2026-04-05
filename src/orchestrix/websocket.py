"""WebSocket hub — broadcasts job and workflow status changes to connected clients."""

import json
import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts events by topic."""

    def __init__(self):
        # topic -> set of websocket connections
        self._subscribers: dict[str, set[WebSocket]] = defaultdict(set)
        # all connections (for broadcast-all)
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, topics: list[str] | None = None):
        await websocket.accept()
        self._connections.add(websocket)
        for topic in topics or ["*"]:
            self._subscribers[topic].add(websocket)
        logger.info("WebSocket connected (topics=%s)", topics or ["*"])

    def disconnect(self, websocket: WebSocket):
        self._connections.discard(websocket)
        for topic_subs in self._subscribers.values():
            topic_subs.discard(websocket)

    async def broadcast(self, topic: str, data: dict):
        """Send a message to all subscribers of a topic and wildcard subscribers."""
        message = json.dumps({"topic": topic, "data": data})
        targets = self._subscribers.get(topic, set()) | self._subscribers.get(
            "*", set()
        )
        dead = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# Singleton manager
manager = ConnectionManager()


async def notify_job_update(job_id: str, status: str, extra: dict | None = None):
    """Emit a job status change event."""
    data = {"job_id": job_id, "status": status, **(extra or {})}
    await manager.broadcast("job.update", data)


async def notify_workflow_update(run_id: str, status: str, extra: dict | None = None):
    """Emit a workflow run status change event."""
    data = {"run_id": run_id, "status": status, **(extra or {})}
    await manager.broadcast("workflow.update", data)


async def notify_worker_update(worker_id: str, status: str, extra: dict | None = None):
    """Emit a worker status change event."""
    data = {"worker_id": worker_id, "status": status, **(extra or {})}
    await manager.broadcast("worker.update", data)
