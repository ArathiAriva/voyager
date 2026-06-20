"""Tests for connected content endpoints."""
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

TRIP_PAYLOAD = {
    "destination": "Lisbon, Portugal",
    "dates": "August 2025",
    "status": "past",
    "emoji": "🌊",
    "summary": "Fado and pastéis.",
}


async def _create_trip(client: AsyncClient) -> str:
    resp = await client.post("/api/trips", json=TRIP_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["id"]


# ── CRUD ─────────────────────────────────────────────────────────────────────

async def test_list_content_empty(client: AsyncClient):
    trip_id = await _create_trip(client)
    resp = await client.get(f"/api/trips/{trip_id}/content")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_add_content_fetches_og_metadata(client: AsyncClient):
    trip_id = await _create_trip(client)
    with patch("app.routers.content._fetch_og_metadata", new_callable=AsyncMock, return_value=("My Photo Album", "https://example.com/thumb.jpg")):
        resp = await client.post(f"/api/trips/{trip_id}/content", json={
            "url": "https://photos.example.com/album/lisbon",
            "type": "album",
        })
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "My Photo Album"
    assert data["thumbnail_url"] == "https://example.com/thumb.jpg"
    assert data["trip_id"] == trip_id
    assert data["type"] == "album"


async def test_add_content_og_failure_still_saves(client: AsyncClient):
    trip_id = await _create_trip(client)
    with patch("app.routers.content._fetch_og_metadata", new_callable=AsyncMock, return_value=(None, None)):
        resp = await client.post(f"/api/trips/{trip_id}/content", json={
            "url": "https://www.instagram.com/p/abc123",
            "type": "instagram",
        })
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] is None
    assert data["thumbnail_url"] is None
    assert data["url"] == "https://www.instagram.com/p/abc123"


async def test_list_content_multiple(client: AsyncClient):
    trip_id = await _create_trip(client)
    with patch("app.routers.content._fetch_og_metadata", new_callable=AsyncMock, return_value=(None, None)):
        await client.post(f"/api/trips/{trip_id}/content", json={"url": "https://example.com/1", "type": "blog"})
        await client.post(f"/api/trips/{trip_id}/content", json={"url": "https://example.com/2", "type": "album"})

    resp = await client.get(f"/api/trips/{trip_id}/content")
    assert len(resp.json()) == 2


async def test_delete_content(client: AsyncClient):
    trip_id = await _create_trip(client)
    with patch("app.routers.content._fetch_og_metadata", new_callable=AsyncMock, return_value=(None, None)):
        created = await client.post(f"/api/trips/{trip_id}/content", json={"url": "https://example.com/album", "type": "album"})
    content_id = created.json()["id"]

    resp = await client.delete(f"/api/trips/{trip_id}/content/{content_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/trips/{trip_id}/content")
    assert resp.json() == []


async def test_delete_content_not_found(client: AsyncClient):
    trip_id = await _create_trip(client)
    resp = await client.delete(f"/api/trips/{trip_id}/content/nonexistent")
    assert resp.status_code == 404


async def test_content_trip_not_found(client: AsyncClient):
    resp = await client.get("/api/trips/nonexistent/content")
    assert resp.status_code == 404


async def test_trip_delete_cascades_content(client: AsyncClient):
    trip_id = await _create_trip(client)
    with patch("app.routers.content._fetch_og_metadata", new_callable=AsyncMock, return_value=(None, None)):
        await client.post(f"/api/trips/{trip_id}/content", json={"url": "https://example.com/album", "type": "album"})

    await client.delete(f"/api/trips/{trip_id}")
    resp = await client.get(f"/api/trips/{trip_id}/content")
    assert resp.status_code == 404
