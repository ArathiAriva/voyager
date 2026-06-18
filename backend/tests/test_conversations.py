import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_list_conversations_empty(client: AsyncClient):
    resp = await client.get("/api/conversations")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_conversation(client: AsyncClient):
    resp = await client.post("/api/conversations")
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["title"] == "New conversation"


async def test_get_conversation(client: AsyncClient):
    create = await client.post("/api/conversations")
    conv_id = create.json()["id"]

    resp = await client.get(f"/api/conversations/{conv_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == conv_id
    assert data["messages"] == []


async def test_get_conversation_not_found(client: AsyncClient):
    resp = await client.get("/api/conversations/nonexistent-id")
    assert resp.status_code == 404


async def test_delete_conversation(client: AsyncClient):
    create = await client.post("/api/conversations")
    conv_id = create.json()["id"]

    resp = await client.delete(f"/api/conversations/{conv_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/conversations/{conv_id}")
    assert resp.status_code == 404


async def test_list_conversations_ordered_by_updated_at(client: AsyncClient):
    first = await client.post("/api/conversations")
    second = await client.post("/api/conversations")

    resp = await client.get("/api/conversations")
    ids = [c["id"] for c in resp.json()]
    # Most recently created comes first
    assert ids[0] == second.json()["id"]
    assert ids[1] == first.json()["id"]
