"""
LangGraph multi-agent planning graph.

Flow:
  load_user_context → classify_intent
    → [activities, food, logistics in parallel via Send API]
    → accommodation_researcher
    → optimizer → critic
    → should_revise? (loop max 2x) or assemble_reply
    → persist_itinerary → END

The DB session is passed via LangGraph config["configurable"]["session"] and
extracted inside each node via RunnableConfig.
"""

import logging
from typing import Literal

from langgraph.graph import StateGraph, END
from langgraph.types import Send, RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.planning.state import PlanningState, RevisionScope
from app.agents import planner, activities, food, accommodation, logistics, optimizer, critic
from app.models.orm import TripORM

logger = logging.getLogger("voyager.planning.graph")

ALL_DOMAINS = ["activities", "food", "logistics"]


def _session(config: RunnableConfig) -> AsyncSession:
    return config["configurable"]["session"]


async def _emit(config: RunnableConfig, label: str) -> None:
    emit = config["configurable"].get("emit_step")
    if emit:
        await emit(label)


# ── Node functions ────────────────────────────────────────────────────────────

async def node_load_context(state: PlanningState, config: RunnableConfig) -> dict:
    await _emit(config, "Loading your travel profile…")
    ctx = await planner.load_user_context(state["user_message"], _session(config))
    return {
        "user_preferences": ctx["preferences"],
        "past_trips": ctx["past_trips"],
        "saved_places": ctx["saved_places"],
    }


async def node_classify_intent(state: PlanningState, config: RunnableConfig) -> dict:
    await _emit(config, "Understanding your request…")
    session = _session(config)
    result = await planner.classify_intent(state["user_message"])
    intent = result.get("intent", "not_planning")
    domains = result.get("revision_domains") or ALL_DOMAINS
    day_range = result.get("day_range")
    instruction = result.get("instruction", state["user_message"])
    missing = result.get("missing", [])

    revision_scope: RevisionScope = {
        "domains": domains if intent in ("full_plan", "revision") else [],
        "day_range": tuple(day_range) if day_range else None,
        "instruction": instruction,
    }

    updates: dict = {
        "revision_scope": revision_scope,
        "revision_count": state.get("revision_count", 0),
        "activities": [],
        "food": [],
        "logistics": [],
        "accommodation": [],
        "missing_info": missing,
    }

    if intent == "needs_info":
        # Don't build a brief or load context — clarify node will handle the reply
        return updates

    ctx = {
        "preferences": state.get("user_preferences", []),
        "past_trips": state.get("past_trips", []),
        "saved_places": state.get("saved_places", []),
    }
    brief = await planner.build_brief(state["user_message"], ctx)
    updates["brief"] = brief

    # Load existing itinerary for revisions
    existing = None
    trip_id = state.get("trip_id")
    if trip_id and intent == "revision":
        trip = await session.get(TripORM, trip_id)
        if trip and trip.itinerary:
            existing = trip.itinerary
    updates["existing_itinerary"] = existing

    return updates


async def node_clarify(state: PlanningState, config: RunnableConfig) -> dict:
    """Ask the user for missing planning details instead of running the full graph."""
    missing = state.get("missing_info", ["destination", "duration"])
    reply = await planner.build_clarification(missing, state["user_message"])
    return {"final_reply": reply}


async def node_activities(state: PlanningState, config: RunnableConfig) -> dict:
    await _emit(config, "Researching activities…")
    return await activities.run(state, _session(config))


async def node_food(state: PlanningState, config: RunnableConfig) -> dict:
    await _emit(config, "Researching food & restaurants…")
    return await food.run(state, _session(config))


async def node_logistics(state: PlanningState, config: RunnableConfig) -> dict:
    await _emit(config, "Checking transport & logistics…")
    return await logistics.run(state, _session(config))


async def node_accommodation(state: PlanningState, config: RunnableConfig) -> dict:
    await _emit(config, "Finding accommodation options…")
    return await accommodation.run(state, _session(config))


async def node_optimizer(state: PlanningState, config: RunnableConfig) -> dict:
    await _emit(config, "Building your day-by-day itinerary…")
    return await optimizer.run(state, _session(config))


async def node_critic(state: PlanningState, config: RunnableConfig) -> dict:
    await _emit(config, "Reviewing itinerary quality…")
    return await critic.run(state, _session(config))


async def node_assemble_reply(state: PlanningState, config: RunnableConfig) -> dict:
    await _emit(config, "Assembling your itinerary…")
    reply = await planner.assemble_reply(
        state.get("brief", {}),
        state.get("itinerary_draft", []),
        state.get("unplaced_items", []),
        state.get("conflicts", []),
    )
    return {"final_reply": reply}


async def node_persist_itinerary(state: PlanningState, config: RunnableConfig) -> dict:
    session = _session(config)
    trip_id = state.get("trip_id")
    draft = state.get("itinerary_draft", [])
    if trip_id and draft:
        await planner.persist_itinerary(trip_id, draft, session)
        await _auto_save_places(state, trip_id, session)
    return {}


async def _auto_save_places(state: PlanningState, trip_id: str, session: AsyncSession) -> None:
    """Save LLM-recommended places from researcher outputs into Saved Places."""
    from app.tools import execute_tool
    from app.models.orm import SavedPlaceORM
    from sqlalchemy import select

    # Build a set of already-saved names for this trip to avoid duplicates
    existing_result = await session.execute(
        select(SavedPlaceORM.name).where(SavedPlaceORM.trip_id == trip_id)
    )
    existing_names: set[str] = {row[0].lower() for row in existing_result.fetchall()}

    # Collect all recommended places from researchers (skip "saved" — already in DB)
    candidates: list[dict] = []
    for item in state.get("activities", []):
        if item.get("source") != "saved":
            candidates.append({**item, "_category": item.get("category", "attraction")})
    for item in state.get("food", []):
        if item.get("source") != "saved":
            candidates.append({**item, "_category": item.get("category", "restaurant")})
    for item in state.get("accommodation", []):
        if item.get("source") != "saved":
            candidates.append({**item, "_category": "hotel"})

    saved_count = 0
    for place in candidates:
        name = place.get("name", "").strip()
        if not name or name.lower() in existing_names:
            continue
        existing_names.add(name.lower())
        notes_parts = []
        if place.get("notes"):
            notes_parts.append(place["notes"])
        if place.get("cuisine"):
            notes_parts.append(f"Cuisine: {place['cuisine']}")
        if place.get("price_tier"):
            notes_parts.append(f"Price: {place['price_tier']}")
        if place.get("why_convenient"):
            notes_parts.append(place["why_convenient"])
        destination = state.get("brief", {}).get("destination", "")
        query = f"{name} {destination}".strip()
        maps_url = f"https://maps.google.com/?q={query.replace(' ', '+')}"
        try:
            await execute_tool("save_place", {
                "trip_id": trip_id,
                "name": name,
                "category": place["_category"],
                "area": place.get("area"),
                "notes": " | ".join(notes_parts) if notes_parts else None,
                "url": maps_url,
            }, session)
            saved_count += 1
        except Exception:
            logger.warning("persist | failed to auto-save place: %s", name)

    logger.info("persist | auto-saved %d recommended places for trip %s", saved_count, trip_id[:8])


async def node_targeted_revision(state: PlanningState, config: RunnableConfig) -> dict:
    """Narrow revision_scope to only the domains the Critic flagged, then loop."""
    issues = state.get("critique_issues", [])
    flagged: set[str] = set()
    for issue in issues:
        desc = (issue.get("description") or "").lower()
        if any(w in desc for w in ("food", "lunch", "dinner", "restaurant", "cafe")):
            flagged.add("food")
        if any(w in desc for w in ("activity", "attraction", "museum", "temple")):
            flagged.add("activities")
        if any(w in desc for w in ("hotel", "accommodation", "stay")):
            flagged.add("accommodation")
        if any(w in desc for w in ("transport", "travel", "transfer", "logistics")):
            flagged.add("logistics")
    if not flagged:
        flagged = set(ALL_DOMAINS)

    current_scope = state.get("revision_scope", {})
    return {
        "revision_scope": {
            **current_scope,
            "domains": list(flagged),
            "instruction": f"Fix issues: {[i.get('description', '') for i in issues]}",
        },
        "revision_count": state.get("revision_count", 0) + 1,
        "activities": [] if "activities" in flagged else state.get("activities", []),
        "food": [] if "food" in flagged else state.get("food", []),
        "logistics": [] if "logistics" in flagged else state.get("logistics", []),
    }


# ── Routing ───────────────────────────────────────────────────────────────────

def route_after_classify(state: PlanningState) -> Literal["clarify", "assemble_reply"] | list[Send]:
    """Route after classify_intent: clarify if info missing, fan-out to researchers otherwise."""
    if state.get("missing_info"):
        return "clarify"

    domains = state.get("revision_scope", {}).get("domains", [])
    if not domains:
        return "assemble_reply"

    sends = []
    if "activities" in domains:
        sends.append(Send("activities_researcher", state))
    if "food" in domains:
        sends.append(Send("food_researcher", state))
    if "logistics" in domains:
        sends.append(Send("logistics_researcher", state))

    return sends if sends else "accommodation_researcher"


def should_revise(state: PlanningState) -> Literal["revise", "proceed"]:
    score = state.get("critique_score", 5)
    revision_count = state.get("revision_count", 0)
    if score < 4 and revision_count < 2:
        logger.info("graph | score=%d revision_count=%d → revising", score, revision_count)
        return "revise"
    return "proceed"


# ── Graph assembly ────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    g = StateGraph(PlanningState)

    g.add_node("load_context", node_load_context)
    g.add_node("classify_intent", node_classify_intent)
    g.add_node("clarify", node_clarify)
    g.add_node("activities_researcher", node_activities)
    g.add_node("food_researcher", node_food)
    g.add_node("logistics_researcher", node_logistics)
    g.add_node("accommodation_researcher", node_accommodation)
    g.add_node("optimizer", node_optimizer)
    g.add_node("critic", node_critic)
    g.add_node("targeted_revision", node_targeted_revision)
    g.add_node("assemble_reply", node_assemble_reply)
    g.add_node("persist_itinerary", node_persist_itinerary)

    g.set_entry_point("load_context")
    g.add_edge("load_context", "classify_intent")

    g.add_conditional_edges("classify_intent", route_after_classify)
    g.add_edge("clarify", END)

    # All parallel researchers fan back into accommodation
    g.add_edge("activities_researcher", "accommodation_researcher")
    g.add_edge("food_researcher", "accommodation_researcher")
    g.add_edge("logistics_researcher", "accommodation_researcher")

    g.add_edge("accommodation_researcher", "optimizer")
    g.add_edge("optimizer", "critic")

    g.add_conditional_edges(
        "critic",
        should_revise,
        {"revise": "targeted_revision", "proceed": "assemble_reply"},
    )

    # Revision loop goes back to accommodation (after targeted_revision re-populates researcher outputs)
    g.add_edge("targeted_revision", "accommodation_researcher")

    g.add_edge("assemble_reply", "persist_itinerary")
    g.add_edge("persist_itinerary", END)

    return g.compile()


planning_graph = build_graph()
