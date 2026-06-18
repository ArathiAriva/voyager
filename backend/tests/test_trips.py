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
