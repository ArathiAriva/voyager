"""Tests for journal entry endpoints."""
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

TRIP_PAYLOAD = {
    "destination": "Tokyo, Japan",
    "dates": "April 2025",
    "status": "past",
    "emoji": "🗼",
    "summary": "First time in Japan.",
}


async def _create_trip(client: AsyncClient) -> str:
    resp = await client.post("/api/trips", json=TRIP_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["id"]


# ── CRUD ─────────────────────────────────────────────────────────────────────

async def test_list_journal_entries_empty(client: AsyncClient):
    trip_id = await _create_trip(client)
    resp = await client.get(f"/api/trips/{trip_id}/journal")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_journal_entry(client: AsyncClient):
    trip_id = await _create_trip(client)
    with patch("app.routers.journal._extract_journal_memory", new_callable=AsyncMock):
        resp = await client.post(f"/api/trips/{trip_id}/journal", json={
            "date": "2025-04-10",
            "body": "Walked through Yanaka — quiet and old-Tokyo feeling.",
            "source": "app",
        })
    assert resp.status_code == 201
    data = resp.json()
    assert data["date"] == "2025-04-10"
    assert data["trip_id"] == trip_id
    assert data["source"] == "app"


async def test_list_journal_entries_ordered_by_date_desc(client: AsyncClient):
    trip_id = await _create_trip(client)
    with patch("app.routers.journal._extract_journal_memory", new_callable=AsyncMock):
        await client.post(f"/api/trips/{trip_id}/journal", json={"date": "2025-04-08", "body": "Day 1"})
        await client.post(f"/api/trips/{trip_id}/journal", json={"date": "2025-04-10", "body": "Day 3"})
        await client.post(f"/api/trips/{trip_id}/journal", json={"date": "2025-04-09", "body": "Day 2"})

    resp = await client.get(f"/api/trips/{trip_id}/journal")
    dates = [e["date"] for e in resp.json()]
    assert dates == ["2025-04-10", "2025-04-09", "2025-04-08"]


async def test_update_journal_entry(client: AsyncClient):
    trip_id = await _create_trip(client)
    with patch("app.routers.journal._extract_journal_memory", new_callable=AsyncMock):
        created = await client.post(f"/api/trips/{trip_id}/journal", json={"date": "2025-04-10", "body": "Original"})
    entry_id = created.json()["id"]

    resp = await client.patch(f"/api/trips/{trip_id}/journal/{entry_id}", json={"body": "Updated"})
    assert resp.status_code == 200
    assert resp.json()["body"] == "Updated"


async def test_delete_journal_entry(client: AsyncClient):
    trip_id = await _create_trip(client)
    with patch("app.routers.journal._extract_journal_memory", new_callable=AsyncMock):
        created = await client.post(f"/api/trips/{trip_id}/journal", json={"date": "2025-04-10", "body": "To delete"})
    entry_id = created.json()["id"]

    resp = await client.delete(f"/api/trips/{trip_id}/journal/{entry_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/trips/{trip_id}/journal")
    assert resp.json() == []


async def test_journal_entry_not_found(client: AsyncClient):
    trip_id = await _create_trip(client)
    resp = await client.patch(f"/api/trips/{trip_id}/journal/nonexistent", json={"body": "x"})
    assert resp.status_code == 404


async def test_journal_entry_trip_not_found(client: AsyncClient):
    resp = await client.get("/api/trips/nonexistent/journal")
    assert resp.status_code == 404


async def test_trip_delete_cascades_journal_entries(client: AsyncClient):
    trip_id = await _create_trip(client)
    with patch("app.routers.journal._extract_journal_memory", new_callable=AsyncMock):
        await client.post(f"/api/trips/{trip_id}/journal", json={"date": "2025-04-10", "body": "Entry"})

    await client.delete(f"/api/trips/{trip_id}")
    # Trip is gone, listing journal should 404
    resp = await client.get(f"/api/trips/{trip_id}/journal")
    assert resp.status_code == 404
