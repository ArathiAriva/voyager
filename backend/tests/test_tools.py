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


# ── Itinerary editing safety ────────────────────────────────────────────────

async def test_get_trips_includes_the_itinerary(session_with_trips):
    """The agent cannot safely edit what it cannot read. get_trips returned only
    id/destination/dates/status/summary, so a model asked to change one day had no
    way to see the others -- while set_itinerary replaces all of them."""
    await execute_tool("set_itinerary", {
        "trip_id": "2",
        "days": [{"day": 1, "plan": "Arrive"}, {"day": 2, "plan": "Mercado"}],
    }, session_with_trips)

    trips = json.loads(await execute_tool("get_trips", {}, session_with_trips))["trips"]
    oaxaca = next(t for t in trips if t["id"] == "2")
    assert [d["day"] for d in oaxaca["itinerary"]] == [1, 2]


async def test_set_itinerary_refuses_to_truncate_an_existing_itinerary(session_with_trips):
    """The silent-truncation path: asked to 'change day 3', a model that passes back
    only day 3 would delete days 1, 2 and 4. Unrecoverable and invisible, so the
    server refuses rather than trusting the prompt."""
    days = [{"day": i, "plan": f"Day {i}"} for i in range(1, 5)]
    await execute_tool("set_itinerary", {"trip_id": "2", "days": days}, session_with_trips)

    result = json.loads(await execute_tool("set_itinerary", {
        "trip_id": "2",
        "days": [{"day": 3, "plan": "Citadel instead"}],
    }, session_with_trips))

    assert "error" in result
    assert result["existing_days"] == 4 and result["submitted_days"] == 1

    trips = json.loads(await execute_tool("get_trips", {}, session_with_trips))["trips"]
    oaxaca = next(t for t in trips if t["id"] == "2")
    assert len(oaxaca["itinerary"]) == 4, "days must survive a refused truncation"


async def test_set_itinerary_allows_a_full_replace_with_one_day_changed(session_with_trips):
    """The correct edit path stays available -- the guard must not block real edits."""
    days = [{"day": i, "plan": f"Day {i}"} for i in range(1, 5)]
    await execute_tool("set_itinerary", {"trip_id": "2", "days": days}, session_with_trips)

    days[2] = {"day": 3, "plan": "Citadel instead"}
    result = json.loads(await execute_tool("set_itinerary", {"trip_id": "2", "days": days}, session_with_trips))
    assert result["action"] == "itinerary_saved" and result["days"] == 4

    trips = json.loads(await execute_tool("get_trips", {}, session_with_trips))["trips"]
    oaxaca = next(t for t in trips if t["id"] == "2")
    assert oaxaca["itinerary"][2]["plan"] == "Citadel instead"


async def test_set_itinerary_allows_growing_and_first_write(session_with_trips):
    """Adding days, and the initial write against no existing itinerary, are both
    legitimate and must not trip the guard."""
    first = json.loads(await execute_tool("set_itinerary", {
        "trip_id": "1", "days": [{"day": 1, "plan": "Arrive"}],
    }, session_with_trips))
    assert first["action"] == "itinerary_saved"

    grown = json.loads(await execute_tool("set_itinerary", {
        "trip_id": "1",
        "days": [{"day": 1, "plan": "Arrive"}, {"day": 2, "plan": "Temples"}],
    }, session_with_trips))
    assert grown["days"] == 2
