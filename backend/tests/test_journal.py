"""Tests for journal entry endpoints."""
import asyncio
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


# ── Cost attribution (B-5) ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_journal_extraction_is_attributed_to_memory_extraction():
    """B-5: _extract_journal_memory made an LLM call without setting a usage
    context, so its cost was attributed to whatever context happened to be current
    when the task was spawned. That made `memory_extraction` an undercount of real
    extraction spend -- the number M-6's "not worth fixing" call rests on."""
    from unittest.mock import MagicMock
    from app.routers.journal import _extract_journal_memory
    from app.usage import usage_context

    seen: list[str] = []

    async def fake_create(*args, **kwargs):
        # Captured at call time, which is what the usage recorder reads.
        seen.append(usage_context.get())
        message = MagicMock()
        message.content = '{"episode": "A day in Petra.", "preferences": []}'
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        return response

    client = MagicMock()
    client.chat.completions.create = fake_create

    # Spawn under a *different* context, as a real request would.
    usage_context.set("chat")
    with patch("app.routers.journal.get_client", return_value=client), \
         patch("app.routers.journal.mem.store_episode"), \
         patch("app.routers.journal.mem.store_preferences"):
        await _extract_journal_memory("entry-1", "Petra, Jordan", "Walked the Siq at dawn.")

    assert seen == ["memory_extraction"]


@pytest.mark.asyncio
async def test_journal_extraction_does_not_leak_its_context_to_the_caller():
    """ContextVar.set inside a task must not alter the spawning context. If it did,
    every request that created a journal entry would log its later LLM calls as
    memory_extraction."""
    from unittest.mock import MagicMock
    from app.routers.journal import _extract_journal_memory
    from app.usage import usage_context

    async def fake_create(*args, **kwargs):
        message = MagicMock()
        message.content = '{"episode": "x", "preferences": []}'
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        return response

    client = MagicMock()
    client.chat.completions.create = fake_create

    usage_context.set("chat")
    with patch("app.routers.journal.get_client", return_value=client), \
         patch("app.routers.journal.mem.store_episode"), \
         patch("app.routers.journal.mem.store_preferences"):
        await asyncio.create_task(
            _extract_journal_memory("entry-2", "Petra, Jordan", "Another entry.")
        )

    assert usage_context.get() == "chat"
