from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from orchestrix.api.auth import router as auth_router
from orchestrix.api.events import router as events_router
from orchestrix.api.jobs import queue_router, recurring_router, router as jobs_router
from orchestrix.api.metrics import router as metrics_router
from orchestrix.api.workers import router as workers_router
from orchestrix.api.workflows import router as workflows_router
from orchestrix.api.ws import router as ws_router
from orchestrix.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    from orchestrix.telemetry import instrument_fastapi, setup_telemetry
    setup_telemetry(service_name="orchestrix-api")
    instrument_fastapi(app)
    yield
    await engine.dispose()


app = FastAPI(
    title="Orchestrix Engine",
    description="Distributed async job & workflow execution engine",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(jobs_router)
app.include_router(events_router)
app.include_router(workers_router)
app.include_router(workflows_router)
app.include_router(queue_router)
app.include_router(recurring_router)
app.include_router(metrics_router)
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
