"""Shared test fixtures — async database, session, test client."""

import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from orchestrix.models.tables import Base

# Use an in-memory SQLite database for unit tests.
# For integration tests against real Postgres, override TEST_DATABASE_URL env var.
TEST_DATABASE_URL = "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true"


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def async_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional session that rolls back after each test.

    Uses join_transaction_block so that session.commit() inside business logic
    only releases a SAVEPOINT instead of truly committing, keeping each test
    fully isolated.
    """
    async with async_engine.connect() as conn:
        await conn.begin()
        async with AsyncSession(bind=conn, join_transaction_mode="rollback_only", expire_on_commit=False) as sess:
            yield sess
        await conn.rollback()


@pytest_asyncio.fixture
async def client(async_engine) -> AsyncGenerator[AsyncClient, None]:
    """HTTPX async client wired to the FastAPI app with overridden DB session."""
    from orchestrix.api.app import app
    from orchestrix.database import get_session

    async with async_engine.connect() as conn:
        await conn.begin()

        async def _override_session():
            async with AsyncSession(bind=conn, join_transaction_mode="rollback_only", expire_on_commit=False) as sess:
                yield sess

        app.dependency_overrides[get_session] = _override_session
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
        app.dependency_overrides.clear()
        await conn.rollback()
