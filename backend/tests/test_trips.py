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


# ── place category enum vs. write paths (B-7) ───────────────────────────────

def test_coerce_category_maps_free_text_onto_the_enum():
    """B-7: LLM extraction and save_place args are not schema-checked, so they could
    write a category the `list[SavedPlace]` response model cannot serialise -- which
    500'd GET /trips/{id}/places for the whole trip."""
    from app.models.trip import coerce_category, PLACE_CATEGORIES

    assert "street food" in PLACE_CATEGORIES
    assert coerce_category("street food") == "street food"
    assert coerce_category("Street Food") == "street food"
    assert coerce_category("street_food") == "street food"
    assert coerce_category("ramen shop") == "other"
    assert coerce_category(None) == "other"
    assert coerce_category("") == "other"


def test_tool_schema_enums_track_the_category_source_of_truth():
    """The save_place / search_places schemas used to hardcode the list, so widening
    the enum would silently leave them stale."""
    from app.models.trip import PLACE_CATEGORIES
    from app.tools import TOOL_SCHEMAS

    found = 0
    for tool in TOOL_SCHEMAS:
        props = tool["function"].get("parameters", {}).get("properties", {})
        enum = props.get("category", {}).get("enum")
        if enum:
            found += 1
            assert tuple(enum) == PLACE_CATEGORIES
    assert found == 2


async def test_places_endpoint_serves_every_valid_category(client: AsyncClient):
    """A row in any valid category must not break the listing for the whole trip."""
    trip = await client.post("/api/trips", json={
        "destination": "Bangkok, Thailand", "dates": "Jan 2026",
        "status": "upcoming", "emoji": "🇹🇭",
    })
    trip_id = trip.json()["id"]

    from app.models.trip import PLACE_CATEGORIES
    for i, category in enumerate(PLACE_CATEGORIES):
        resp = await client.post(f"/api/trips/{trip_id}/places", json={
            "name": f"Place {i}", "category": category,
        })
        assert resp.status_code == 201, (category, resp.text)

    listing = await client.get(f"/api/trips/{trip_id}/places")
    assert listing.status_code == 200, listing.text
    assert len(listing.json()) == len(PLACE_CATEGORIES)


# ── planning run traces ─────────────────────────────────────────────────────

def test_summarise_describes_each_agent_by_what_it_produced():
    """The timeline is only readable if each node's line says something specific;
    a generic key dump would defeat the point of the page."""
    from app.planning.trace import summarise

    assert summarise("build_brief", {"brief": {"destination": "Lisbon", "duration_days": 3}}) == "Lisbon · 3 days"
    assert summarise("critic", {"critique_score": 4, "critique_issues": ["a", "b"]}) == "score 4/5 · 2 issue(s)"
    assert summarise("food_researcher", {"food": [{"area": "Alfama"}, {"area": "Belem"}]}) == "2 food options across 2 areas"
    assert summarise("optimizer", {"itinerary_draft": [1, 2, 3], "unplaced_items": []}) == "3 day(s) drafted"
    assert summarise("load_context", {"user_preferences": ["x"], "saved_places": [], "past_trips": [1]}) \
        == "1 preferences · 0 saved places · 1 past trips"


def test_summarise_never_raises_on_unexpected_shapes():
    """Tracing is fail-open; a malformed delta must not break a planning run."""
    from app.planning.trace import summarise

    assert isinstance(summarise("critic", {}), str)
    assert isinstance(summarise("unknown_node", {"a": 1}), str)
    assert isinstance(summarise("food_researcher", {"food": "not a list"}), str)


def test_planning_trace_records_a_run_and_its_steps(tmp_path):
    import asyncio
    import app.db as db
    from app.models.orm import Base, PlanningRunORM
    from app.planning import trace as pt
    from datetime import datetime, timezone
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    original = db.DB_PATH
    db.reconfigure(f"sqlite+aiosqlite:///{tmp_path}/planning.db")

    async def scenario():
        async with db.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        run_id = await pt.start_run("conv-1", "plan my 3 days in Lisbon")
        assert run_id
        now = datetime.now(timezone.utc)
        await pt.record_step(run_id, 0, "build_brief", "", {"brief": {"destination": "Lisbon"}}, 10.0, now)
        await pt.record_step(run_id, 1, "critic", "", {"critique_score": 4, "critique_issues": []}, 20.0, now)
        await pt.finish_run(run_id, status="complete",
                            final_state={"brief": {"destination": "Lisbon"}, "critique_score": 4},
                            duration_ms=1234.0)

        async with db.SessionLocal() as session:
            run = (await session.execute(
                select(PlanningRunORM).options(selectinload(PlanningRunORM.steps))
            )).scalar_one()
        assert run.status == "complete"
        assert run.destination == "Lisbon"
        assert run.critic_score == 4
        assert [s.node for s in sorted(run.steps, key=lambda s: s.seq)] == ["build_brief", "critic"]

    try:
        asyncio.run(scenario())
    finally:
        db.reconfigure(original)


def test_planning_trace_helpers_are_noops_without_a_run_id():
    """start_run returns None when tracing fails; downstream calls must tolerate it."""
    import asyncio
    from datetime import datetime, timezone
    from app.planning import trace as pt

    asyncio.run(pt.record_step(None, 0, "critic", "", {}, 1.0, datetime.now(timezone.utc)))
    asyncio.run(pt.finish_run(None, status="complete"))
