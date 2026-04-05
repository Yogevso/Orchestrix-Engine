from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrix.database import get_session
from orchestrix.engine import core
from orchestrix.models.enums import JobEventType
from orchestrix.schemas import EventListResponse, JobEventResponse

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventListResponse)
async def list_events(
    since: datetime | None = Query(
        None, description="Only return events created at or after this timestamp"
    ),
    event_type: JobEventType | None = Query(None, description="Filter by event type"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """List job events across all jobs. Designed for downstream consumers like Orchestrix AI."""
    events, total = await core.list_events(
        session,
        since=since,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    return EventListResponse(
        events=[JobEventResponse.model_validate(e) for e in events],
        total=total,
    )
