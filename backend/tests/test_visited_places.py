"""Marking a saved place as visited (Stage 1).

Design: docs/visited-places-and-anecdotes.md

A place the user booked and loved and one they bookmarked and skipped were the
same row, so "where did I actually eat in Rome" was unanswerable and the app
could re-recommend somewhere they had already been.
"""

import pytest


@pytest.fixture(autouse=True)
def isolated_places(monkeypatch):
    """Fresh in-memory places collection, so these never touch a real profile."""
    import chromadb
    import app.memory as mem

    client = chromadb.EphemeralClient()
    try:
        client.delete_collection("places_test")
    except Exception:
        pass
    collection = client.get_or_create_collection("places_test")
    monkeypatch.setattr(mem, "_places", lambda: collection)
    return collection


async def _trip(client) -> str:
    resp = await client.post("/api/trips", json={
        "destination": "Rome, Italy", "dates": "May 2026", "status": "past", "emoji": "🇮🇹"})
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_places_are_not_visited_by_default(client):
    """Not-visited needs no user action -- it is the honest default for every
    existing row, and for anything the agent saves on the user's behalf."""
    trip_id = await _trip(client)
    place = (await client.post(f"/api/trips/{trip_id}/places", json={
        "name": "Roscioli", "category": "restaurant"})).json()

    assert place["visited"] is False
    assert place["visited_at"] is None


@pytest.mark.asyncio
async def test_marking_visited_records_the_date(client):
    trip_id = await _trip(client)
    place = (await client.post(f"/api/trips/{trip_id}/places", json={
        "name": "Roscioli", "category": "restaurant"})).json()

    updated = (await client.patch(f"/api/trips/{trip_id}/places/{place['id']}", json={
        "visited": True, "visited_at": "2026-05-02"})).json()

    assert updated["visited"] is True
    assert updated["visited_at"] == "2026-05-02"


@pytest.mark.asyncio
async def test_visited_can_be_unset(client):
    """A boolean, not a one-way latch -- marking a place visited by mistake has to
    be reversible."""
    trip_id = await _trip(client)
    place = (await client.post(f"/api/trips/{trip_id}/places", json={
        "name": "Roscioli", "category": "restaurant"})).json()

    await client.patch(f"/api/trips/{trip_id}/places/{place['id']}", json={"visited": True})
    back = (await client.patch(f"/api/trips/{trip_id}/places/{place['id']}",
                               json={"visited": False})).json()

    assert back["visited"] is False


@pytest.mark.asyncio
async def test_retrieval_can_separate_visited_from_merely_saved(client):
    """The point of the flag: "where did I eat in Rome" and "where could I eat in
    Rome" are different questions, and the store could not tell them apart."""
    from app import memory

    trip_id = await _trip(client)
    ids = {}
    for name in ("Roscioli", "Da Enzo", "Armando al Pantheon"):
        resp = await client.post(f"/api/trips/{trip_id}/places", json={
            "name": name, "category": "restaurant",
            "notes": f"{name} is a Roman restaurant serving pasta"})
        ids[name] = resp.json()["id"]

    await client.patch(f"/api/trips/{trip_id}/places/{ids['Roscioli']}", json={"visited": True})

    query = "Roman restaurant pasta"
    went = {h["name"] for h in memory.search_saved_places(query, destination="Rome", visited=True)}
    not_went = {h["name"] for h in memory.search_saved_places(query, destination="Rome", visited=False)}
    both = {h["name"] for h in memory.search_saved_places(query, destination="Rome")}

    assert went == {"Roscioli"}
    assert not_went == {"Da Enzo", "Armando al Pantheon"}
    assert both == went | not_went, "omitting the filter must not narrow anything"


@pytest.mark.asyncio
async def test_visited_survives_a_later_edit(client):
    """PATCH re-embeds the place, so the flag has to be carried into the metadata
    on every write -- not just the one that set it."""
    from app import memory

    trip_id = await _trip(client)
    place = (await client.post(f"/api/trips/{trip_id}/places", json={
        "name": "Roscioli", "category": "restaurant", "notes": "Roman pasta"})).json()

    await client.patch(f"/api/trips/{trip_id}/places/{place['id']}", json={"visited": True})
    await client.patch(f"/api/trips/{trip_id}/places/{place['id']}", json={"notes": "Roman pasta, great carbonara"})

    hits = memory.search_saved_places("Roman pasta", destination="Rome", visited=True)
    assert [h["name"] for h in hits] == ["Roscioli"]


@pytest.mark.asyncio
async def test_search_places_tool_exposes_the_filter(client):
    """The agent needs it to answer "where did I eat" without a second lookup."""
    import json
    from app.tools import execute_tool, tool_by_name
    from app.db import get_session

    schema = tool_by_name("search_places")["function"]["parameters"]["properties"]
    assert "visited" in schema

    trip_id = await _trip(client)
    place = (await client.post(f"/api/trips/{trip_id}/places", json={
        "name": "Roscioli", "category": "restaurant", "notes": "Roman pasta"})).json()
    await client.patch(f"/api/trips/{trip_id}/places/{place['id']}", json={"visited": True})

    async for session in get_session():
        result = json.loads(await execute_tool(
            "search_places", {"query": "Roman pasta", "destination": "Rome", "visited": True}, session))
        break
    assert any(r["name"] == "Roscioli" for r in result.get("results", []))


# ── Anecdotes (Stages 2-3) ──────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_anecdotes(monkeypatch):
    import chromadb
    import app.memory as mem

    client = chromadb.EphemeralClient()
    try:
        client.delete_collection("anecdotes_test")
    except Exception:
        pass
    collection = client.get_or_create_collection("anecdotes_test")
    monkeypatch.setattr(mem, "_anecdotes", lambda: collection)
    return collection


async def _place(client, trip_id: str, name: str = "Roscioli") -> dict:
    resp = await client.post(f"/api/trips/{trip_id}/places", json={
        "name": name, "category": "restaurant", "notes": f"{name} near Campo de' Fiori"})
    return resp.json()


@pytest.mark.asyncio
async def test_anecdote_is_stored_verbatim(client):
    """The agent never authors or edits this text. Anecdotes are retrieved into
    future recommendations, so a tidied one would feed the model's own register
    back to itself as the user's experience."""
    trip_id = await _trip(client)
    place = await _place(client, trip_id)

    words = "The queue was 40 minutes but the carbonara was worth it."
    created = (await client.post(
        f"/api/trips/{trip_id}/places/{place['id']}/anecdotes", json={"body": words})).json()

    assert created["body"] == words, "stored exactly as written"
    assert created["source"] == "app"


@pytest.mark.asyncio
async def test_writing_an_anecdote_marks_the_place_visited(client):
    """Writing about somewhere is evidence of having been there -- the user should
    not have to state it twice."""
    trip_id = await _trip(client)
    place = await _place(client, trip_id)
    assert place["visited"] is False

    await client.post(f"/api/trips/{trip_id}/places/{place['id']}/anecdotes",
                      json={"body": "Great pasta."})

    places = (await client.get(f"/api/trips/{trip_id}/places")).json()
    assert places[0]["visited"] is True


@pytest.mark.asyncio
async def test_a_place_can_hold_several_anecdotes(client):
    """You go twice, or note different things."""
    trip_id = await _trip(client)
    place = await _place(client, trip_id)

    for text in ("First visit: worth the queue.", "Second visit: quieter on a Tuesday."):
        await client.post(f"/api/trips/{trip_id}/places/{place['id']}/anecdotes",
                          json={"body": text})

    listed = (await client.get(f"/api/trips/{trip_id}/places/{place['id']}/anecdotes")).json()
    assert len(listed) == 2


@pytest.mark.asyncio
async def test_empty_anecdotes_are_rejected(client):
    trip_id = await _trip(client)
    place = await _place(client, trip_id)

    resp = await client.post(f"/api/trips/{trip_id}/places/{place['id']}/anecdotes",
                             json={"body": "   "})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_anecdotes_retrieve_separately_from_place_descriptions(client):
    """Kept in their own collection rather than appended to the place's embed_text.
    "What this place is" and "what happened to me there" are different questions,
    and blurring them would degrade both."""
    from app import memory

    trip_id = await _trip(client)
    place = await _place(client, trip_id)
    await client.post(f"/api/trips/{trip_id}/places/{place['id']}/anecdotes",
                      json={"body": "The queue was 40 minutes but the carbonara was worth it."})

    experience = memory.search_anecdotes("what did they think of the carbonara",
                                         destination="Rome")
    assert [h["place_name"] for h in experience] == ["Roscioli"]

    description = memory.search_saved_places("deli near Campo de Fiori", destination="Rome")
    assert [h["name"] for h in description] == ["Roscioli"], "place search still works"


@pytest.mark.asyncio
async def test_deleting_an_anecdote_removes_its_embedding(client):
    from app import memory

    trip_id = await _trip(client)
    place = await _place(client, trip_id)
    created = (await client.post(
        f"/api/trips/{trip_id}/places/{place['id']}/anecdotes",
        json={"body": "The queue was 40 minutes but the carbonara was worth it."})).json()

    resp = await client.delete(
        f"/api/trips/{trip_id}/places/{place['id']}/anecdotes/{created['id']}")
    assert resp.status_code == 204

    assert memory.search_anecdotes("carbonara", destination="Rome") == []


@pytest.mark.asyncio
async def test_search_anecdotes_tool_frames_them_as_the_users_words(client):
    """The tool result has to say whose words these are, or the model will report
    them as fact about the place."""
    import json
    from app.tools import execute_tool
    from app.db import get_session

    trip_id = await _trip(client)
    place = await _place(client, trip_id)
    await client.post(f"/api/trips/{trip_id}/places/{place['id']}/anecdotes",
                      json={"body": "The queue was 40 minutes but the carbonara was worth it."})

    async for session in get_session():
        result = json.loads(await execute_tool(
            "search_anecdotes", {"query": "carbonara", "destination": "Rome"}, session))
        break

    assert result["results"][0]["place"] == "Roscioli"
    assert "user's own words" in result["note"]
