"""WebSocket API route — clients connect here for live updates."""

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from orchestrix.websocket import manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    topics: str | None = Query(None, description="Comma-separated topics: job.update, workflow.update, worker.update"),
):
    topic_list = topics.split(",") if topics else None
    await manager.connect(websocket, topic_list)
    try:
        while True:
            # Keep connection alive; client can send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
