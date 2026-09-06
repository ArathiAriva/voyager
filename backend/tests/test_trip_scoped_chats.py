"""Trip-scoped conversations, and the duplicate-trip bug they fix (B-13).

Design: docs/trip-scoped-chats.md

The bug is the reason this exists: `_resolve_trip_id` had only a destination
string to work with, and created a new trip whenever its fuzzy match missed --
silently, with the user's first sight of it being a duplicate card.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db import Base
from app.models.orm import ConversationORM, TripORM
from app.planning.graph import _resolve_trip_id


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def _trip(session, destination="Halifax, Nova Scotia") -> str:
    trip_id = str(uuid.uuid4())
    session.add(TripORM(id=trip_id, destination=destination, dates="Sept 4-7, 2026",
                        status="upcoming", emoji="🌊"))
    await session.commit()
    return trip_id


# ── B-13 ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unscoped_conversation_creates_a_duplicate_on_a_fuzzy_miss(session):
    """The bug, pinned. Without a scoped conversation there is nothing but the
    destination string, so a phrasing the fuzzy match misses produces a second trip
    for the same journey. This documents the behaviour the fix routes around."""
    trip_id = await _trip(session)

    state = {"brief": {"destination": "Nova Scotia road trip"}, "conversation_trip_id": None}
    resolved = await _resolve_trip_id(state, session)

    trips = (await session.execute(select(TripORM))).scalars().all()
    assert len(trips) == 2
    assert resolved != trip_id


@pytest.mark.asyncio
async def test_scoped_conversation_uses_its_trip_and_creates_nothing(session):
    """The fix: the conversation's trip settles it, with no matching and no
    creating -- even on the exact phrasing that produced a duplicate above."""
    trip_id = await _trip(session)

    state = {"brief": {"destination": "Nova Scotia road trip"}, "conversation_trip_id": trip_id}
    resolved = await _resolve_trip_id(state, session)

    assert resolved == trip_id
    assert len((await session.execute(select(TripORM))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_scoped_to_a_deleted_trip_falls_back_rather_than_failing(session):
    """A trip can be deleted mid-conversation. Resolution must degrade to the old
    destination-matching path, not raise or silently skip persistence."""
    trip_id = await _trip(session)

    state = {"brief": {"destination": "Halifax"}, "conversation_trip_id": str(uuid.uuid4())}
    resolved = await _resolve_trip_id(state, session)

    assert resolved == trip_id, "should match the real Halifax trip by destination"


@pytest.mark.asyncio
async def test_destination_matching_still_works_for_unscoped_conversations(session):
    """Stage 2 must not replace the existing path, only take precedence over it --
    most conversations are unscoped and still need to resolve."""
    trip_id = await _trip(session)

    state = {"brief": {"destination": "Halifax"}, "conversation_trip_id": None}
    assert await _resolve_trip_id(state, session) == trip_id


# ── API surface ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_conversation_can_be_created_scoped_or_unscoped(client):
    trip = (await client.post("/api/trips", json={
        "destination": "Halifax", "dates": "x", "status": "upcoming", "emoji": "🌊"})).json()

    unscoped = (await client.post("/api/conversations")).json()
    assert unscoped["trip_id"] is None, "unscoped is the default and must stay easy"

    scoped = (await client.post("/api/conversations", json={"trip_id": trip["id"]})).json()
    assert scoped["trip_id"] == trip["id"]


@pytest.mark.asyncio
async def test_creating_with_an_unknown_trip_404s(client):
    resp = await client.post("/api/conversations", json={"trip_id": "no-such-trip"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_scope_can_be_set_and_cleared_mid_conversation(client):
    """Conversations wander -- one starts general and becomes about a trip -- so the
    scope is changeable, not fixed at creation."""
    trip = (await client.post("/api/trips", json={
        "destination": "Halifax", "dates": "x", "status": "upcoming", "emoji": "🌊"})).json()
    conv = (await client.post("/api/conversations")).json()

    updated = (await client.patch(f"/api/conversations/{conv['id']}",
                                  json={"trip_id": trip["id"]})).json()
    assert updated["trip_id"] == trip["id"]

    cleared = (await client.patch(f"/api/conversations/{conv['id']}",
                                  json={"trip_id": None})).json()
    assert cleared["trip_id"] is None


@pytest.mark.asyncio
async def test_deleting_a_trip_unscopes_its_conversations_but_keeps_them(client):
    """Deleting a trip must not delete the conversations about it. The declared
    ondelete="SET NULL" does not do this on its own: SQLite does not enforce foreign
    keys without PRAGMA foreign_keys=ON, which this app does not set."""
    trip = (await client.post("/api/trips", json={
        "destination": "Halifax", "dates": "x", "status": "upcoming", "emoji": "🌊"})).json()
    conv = (await client.post("/api/conversations", json={"trip_id": trip["id"]})).json()

    await client.delete(f"/api/trips/{trip['id']}")

    got = (await client.get(f"/api/conversations/{conv['id']}")).json()
    assert got["id"] == conv["id"], "the transcript is still worth keeping"
    assert got["trip_id"] is None, "must not dangle at a deleted trip"


@pytest.mark.asyncio
async def test_conversations_can_be_listed_by_trip(client):
    """The reverse lookup -- "what did I discuss about Halifax" -- was impossible
    before conversations carried a trip."""
    halifax = (await client.post("/api/trips", json={
        "destination": "Halifax", "dates": "x", "status": "upcoming", "emoji": "🌊"})).json()
    kyoto = (await client.post("/api/trips", json={
        "destination": "Kyoto", "dates": "x", "status": "past", "emoji": "🏯"})).json()

    scoped = (await client.post("/api/conversations", json={"trip_id": halifax["id"]})).json()
    await client.post("/api/conversations", json={"trip_id": kyoto["id"]})
    await client.post("/api/conversations")  # unscoped

    listed = (await client.get(f"/api/conversations?trip_id={halifax['id']}")).json()
    assert [c["id"] for c in listed] == [scoped["id"]]

    everything = (await client.get("/api/conversations")).json()
    assert len(everything) == 3, "an unfiltered list must still return all of them"


@pytest.mark.asyncio
async def test_listing_a_trip_with_no_conversations_is_empty_not_an_error(client):
    trip = (await client.post("/api/trips", json={
        "destination": "Halifax", "dates": "x", "status": "upcoming", "emoji": "🌊"})).json()
    await client.post("/api/conversations")  # unscoped, must not leak into the filter

    assert (await client.get(f"/api/conversations?trip_id={trip['id']}")).json() == []
