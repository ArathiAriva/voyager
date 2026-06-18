import json
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db import Base
from app.models.orm import TripORM
from app.tools import execute_tool

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def session_with_trips():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        session.add_all([
            TripORM(id="1", destination="Kyoto, Japan", dates="March 2025", status="past", emoji="🏯", summary="Temple walks"),
            TripORM(id="2", destination="Oaxaca, Mexico", dates="January 2026", status="upcoming", emoji="🌮", summary="Mezcal trip"),
        ])
        await session.commit()
        yield session
    await engine.dispose()


async def test_get_trips_all(session_with_trips):
    result = await execute_tool("get_trips", {}, session_with_trips)
    data = json.loads(result)
    assert len(data["trips"]) == 2


async def test_get_trips_filter_past(session_with_trips):
    result = await execute_tool("get_trips", {"status": "past"}, session_with_trips)
    data = json.loads(result)
    assert len(data["trips"]) == 1
    assert data["trips"][0]["destination"] == "Kyoto, Japan"


async def test_get_trips_filter_upcoming(session_with_trips):
    result = await execute_tool("get_trips", {"status": "upcoming"}, session_with_trips)
    data = json.loads(result)
    assert len(data["trips"]) == 1
    assert data["trips"][0]["destination"] == "Oaxaca, Mexico"


async def test_get_trips_empty(session_with_trips):
    # Use a fresh empty session
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as empty_session:
        result = await execute_tool("get_trips", {}, empty_session)
        data = json.loads(result)
        assert data["trips"] == []
    await engine.dispose()


async def test_unknown_tool(session_with_trips):
    result = await execute_tool("nonexistent_tool", {}, session_with_trips)
    data = json.loads(result)
    assert "error" in data
