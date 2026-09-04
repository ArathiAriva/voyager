import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_list_trips_empty(client: AsyncClient):
    resp = await client.get("/api/trips")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_trip(client: AsyncClient):
    payload = {
        "destination": "Tokyo, Japan",
        "dates": "March 2026",
        "status": "upcoming",
        "emoji": "🗼",
        "summary": "Cherry blossom trip",
    }
    resp = await client.post("/api/trips", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["destination"] == "Tokyo, Japan"
    assert data["status"] == "upcoming"
    assert "id" in data


async def test_get_trip(client: AsyncClient):
    create = await client.post("/api/trips", json={
        "destination": "Paris, France",
        "dates": "June 2026",
        "status": "upcoming",
        "emoji": "🗼",
        "summary": "Art and food",
    })
    trip_id = create.json()["id"]

    resp = await client.get(f"/api/trips/{trip_id}")
    assert resp.status_code == 200
    assert resp.json()["destination"] == "Paris, France"


async def test_get_trip_not_found(client: AsyncClient):
    resp = await client.get("/api/trips/nonexistent-id")
    assert resp.status_code == 404


async def test_update_trip(client: AsyncClient):
    create = await client.post("/api/trips", json={
        "destination": "Berlin, Germany",
        "dates": "July 2026",
        "status": "upcoming",
        "emoji": "🍺",
        "summary": "",
    })
    trip_id = create.json()["id"]

    resp = await client.patch(f"/api/trips/{trip_id}", json={"status": "past", "summary": "Great trip"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "past"
    assert data["summary"] == "Great trip"
    assert data["destination"] == "Berlin, Germany"


async def test_delete_trip(client: AsyncClient):
    create = await client.post("/api/trips", json={
        "destination": "Lisbon, Portugal",
        "dates": "May 2026",
        "status": "upcoming",
        "emoji": "🌊",
        "summary": "",
    })
    trip_id = create.json()["id"]

    resp = await client.delete(f"/api/trips/{trip_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/trips/{trip_id}")
    assert resp.status_code == 404


async def test_list_trips_returns_all(client: AsyncClient):
    for city in ["Rome", "Madrid", "Athens"]:
        await client.post("/api/trips", json={
            "destination": city,
            "dates": "2026",
            "status": "upcoming",
            "emoji": "✈️",
            "summary": "",
        })
    resp = await client.get("/api/trips")
    assert len(resp.json()) == 3


# ── create_trip idempotency (B-10) ──────────────────────────────────────────

async def _create_via_tool(db_session, **overrides):
    import json
    from app.tools import _execute_create_trip

    args = {
        "destination": "Unionville, Markham, Ontario",
        "dates": "September 5, 2025",
        "status": "upcoming",
        "emoji": "🍂",
    }
    args.update(overrides)
    return json.loads(await _execute_create_trip(args, db_session))


async def test_create_trip_tool_does_not_duplicate(db_session):
    """B-10: asking 'did you save it?' made the model call create_trip again, which
    inserted a second row. The second call must return the existing trip instead."""
    from sqlalchemy import select
    from app.models.orm import TripORM

    first = await _create_via_tool(db_session)
    assert first["action"] == "trip_created"

    second = await _create_via_tool(db_session)
    assert second["action"] == "trip_already_exists"
    assert second["trip"]["id"] == first["trip"]["id"]

    rows = (await db_session.execute(select(TripORM))).scalars().all()
    assert len(rows) == 1


async def test_create_trip_tool_matches_loosely_on_destination(db_session):
    """'Unionville' and 'Unionville, Markham, Ontario' are the same trip."""
    first = await _create_via_tool(db_session)
    second = await _create_via_tool(db_session, destination="Unionville")
    assert second["action"] == "trip_already_exists"
    assert second["trip"]["id"] == first["trip"]["id"]


async def test_create_trip_tool_allows_different_dates(db_session):
    """Same place, genuinely different dates is a different trip -- still allowed."""
    await _create_via_tool(db_session)
    second = await _create_via_tool(db_session, dates="December 2026")
    assert second["action"] == "trip_created"


async def test_create_trip_tool_allows_different_destination(db_session):
    await _create_via_tool(db_session)
    second = await _create_via_tool(db_session, destination="Kyoto, Japan")
    assert second["action"] == "trip_created"
