"""
Planner agent — orchestrator. Handles intent classification, brief construction,
and final reply assembly. The only agent that writes to the DB (via set_itinerary).
"""

import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.claude import llm_call
from app.tools import tools_named, execute_tool
from app.models.orm import TripORM
from app import memory
from app.agents import parse_json_response

logger = logging.getLogger("voyager.agents.planner")

CLASSIFY_PROMPT = """You are a trip planning orchestrator for a travel app.

Analyse the user's message and return JSON only — no prose, no code fences.

{
  "intent": "full_plan" | "revision" | "needs_info" | "not_planning",
  "destination": "city/country if mentioned, else null",
  "duration_days": integer if mentioned, else null,
  "revision_domains": ["activities", "food", "accommodation", "logistics"],
  "day_range": [start_day, end_day] | null,
  "instruction": "user's revision instruction verbatim",
  "missing": ["duration", "destination", "dates"]  // fields needed before planning can start
}

Use "needs_info" when the user wants to plan a trip but hasn't provided enough to build a
good itinerary. A plan needs at minimum: a specific destination AND a duration (number of days
or a date range). If either is missing, return "needs_info" with the missing fields listed.

Use "full_plan" only when destination AND duration are both clear.
For "revision": include only the domains affected by the change.
For "full_plan" or "not_planning": revision_domains = [], day_range = null, instruction = "".

Examples:
- "Plan my 7 days in Kyoto" → full_plan (has destination + duration)
- "Let's plan a trip to Hawaii" → needs_info, missing=["duration"]
- "I want to go somewhere in Asia" → needs_info, missing=["destination", "duration"]
- "Plan a trip" → needs_info, missing=["destination", "duration"]
- "Find cheaper restaurants" → revision, domains=["food"]
- "Change Day 3 to focus on temples" → revision, domains=["activities"], day_range=[3,3]
- "What's the weather like?" → not_planning"""

CLARIFY_PROMPT = """You are Voyager, a warm AI travel companion.

The user wants to plan a trip but hasn't given enough detail yet. Ask for what's missing
in a friendly, conversational way — one or two sentences max. Don't list every possible
question; focus only on what's actually missing.

Missing fields will be provided. Ask naturally, not like a form.

Examples:
- missing duration → "How long are you thinking — a long weekend, a full week?"
- missing destination → "Where are you headed?"
- missing both → "Sounds exciting! Where are you thinking of going, and how long do you have?"

Never start planning or make suggestions about the destination yet."""

BRIEF_PROMPT = """You are a trip planning orchestrator. Given the user's message and their profile,
build a structured planning brief for the research agents.

Return JSON only — no prose, no code fences.

{
  "destination": "City, Country",
  "dates": "human-readable date range or duration",
  "duration_days": integer,
  "user_context": {
    "preferences": ["list of relevant preferences from memory"],
    "past_trips": ["list of relevant past trip destinations"],
    "saved_places": [{"name": "...", "category": "...", "area": "..."}]
  },
  "constraints": {
    "budget": "budget | mid-range | luxury | unknown",
    "dietary": [],
    "must_include": []
  }
}"""

ASSEMBLE_PROMPT = """You are Voyager, a warm and knowledgeable travel companion.
The multi-agent planning system has produced a trip itinerary. Write a friendly,
concise summary (3-5 sentences) to present it to the user. Mention:
- The overall structure/theme of the trip
- 1-2 highlights
- Any conflicts or unplaced items the user should know about
- That the itinerary has been saved to their trip

Do not enumerate every day. Be enthusiastic but not excessive."""

CONTEXT_TOOLS = tools_named("search_memory", "get_trips", "search_places", "search_journal")
WRITE_TOOLS = tools_named("set_itinerary", "update_trip")


async def classify_intent(user_message: str, model: str | None = None) -> dict:
    """Parse user message into intent + revision scope."""
    response = await llm_call(
        messages=[
            {"role": "system", "content": CLASSIFY_PROMPT},
            {"role": "user", "content": user_message},
        ],
        model=model,
    )
    return parse_json_response(response.choices[0].message.content or "")


async def build_clarification(missing: list[str], user_message: str, model: str | None = None) -> str:
    """Return a short clarifying question when the planning brief is incomplete."""
    response = await llm_call(
        messages=[
            {"role": "system", "content": CLARIFY_PROMPT},
            {"role": "user", "content": f"User said: '{user_message}'\nMissing: {', '.join(missing)}"},
        ],
        model=model,
    )
    return (response.choices[0].message.content or "").strip()


# Preferences are stored as trait statements ("prefers guesthouses over hotels"),
# but a planning message is mostly logistics ("I plan to be there between 11am and
# 6pm"). Embedding those against each other matches on the wrong axis: a logged
# query returned five preferences, three of them about *timing*, because the raw
# message was dominated by time-of-day tokens.
#
# Retrieving against facet probes instead asks the question the collection can
# actually answer. The user's message still runs as one probe, so anything it
# genuinely matches is kept; the facets add coverage the raw query never reached.
# Cheap by design -- MiniLM embeddings are local, so this costs no API calls.
PREFERENCE_FACETS = [
    "food and dining preferences",
    "accommodation preferences",
    "pace, timing, and crowd preferences",
    "activities, culture, and sightseeing interests",
    "budget and spending preferences",
    "transport and getting-around preferences",
]


def _merge_preference_hits(hit_lists: list[list[dict]], limit: int) -> list[str]:
    """Flatten multi-probe results into one list, best distance wins per document.

    Facet probes overlap, so the same trait is returned by several of them. Dedupe
    on Chroma ID and keep each row's best (lowest) distance, then rank globally so
    a strong hit from one facet outranks a weak hit from another.
    """
    best: dict[str, dict] = {}
    for hits in hit_lists:
        for hit in hits:
            existing = best.get(hit["id"])
            if existing is None or hit["distance"] < existing["distance"]:
                best[hit["id"]] = hit
    ranked = sorted(best.values(), key=lambda h: h["distance"])
    return [h["document"] for h in ranked[:limit]]


async def load_user_context(
    user_message: str,
    session: AsyncSession,
    model: str | None = None,
    max_preferences: int = 8,
) -> dict:
    """Fetch memory, saved places, and past trips to enrich the planning brief."""
    # Episodes stay on the raw message -- they are conversation summaries, so they
    # share its register and the facet probes would not help.
    mem = memory.search_memory(user_message)

    preference_hits = [mem.get("preference_hits", [])]
    for facet in PREFERENCE_FACETS:
        preference_hits.append(
            memory.search_memory(facet, collections=("semantic",)).get("preference_hits", [])
        )
    preferences = _merge_preference_hits(preference_hits, max_preferences)

    trips_result = await session.execute(select(TripORM))
    trips = trips_result.scalars().all()
    places = memory.search_saved_places(user_message, n_results=20)

    return {
        "preferences": preferences,
        "episodes": mem.get("episodes", []),
        "past_trips": [{"id": t.id, "destination": t.destination, "dates": t.dates, "status": t.status} for t in trips],
        "saved_places": places,
    }


async def build_brief(user_message: str, context: dict, model: str | None = None) -> dict:
    """Construct the structured planning brief for research agents."""
    context_str = json.dumps(context, indent=2)
    response = await llm_call(
        messages=[
            {"role": "system", "content": BRIEF_PROMPT},
            {"role": "user", "content": f"User message: {user_message}\n\nUser profile:\n{context_str}"},
        ],
        model=model,
    )
    return parse_json_response(response.choices[0].message.content or "")


async def assemble_reply(
    brief: dict,
    itinerary_draft: list[dict],
    unplaced_items: list[str],
    conflicts: list[str],
    model: str | None = None,
) -> str:
    """Write the user-facing summary of the completed itinerary."""
    payload = {
        "brief": brief,
        "itinerary": itinerary_draft,
        "unplaced": unplaced_items,
        "conflicts": conflicts,
    }
    response = await llm_call(
        messages=[
            {"role": "system", "content": ASSEMBLE_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ],
        model=model,
    )
    return (response.choices[0].message.content or "").strip()


async def persist_itinerary(trip_id: str, itinerary: list[dict], session: AsyncSession) -> None:
    """Call set_itinerary tool to save the final itinerary to TripORM."""
    await execute_tool("set_itinerary", {"trip_id": trip_id, "days": itinerary}, session)
    logger.info("planner | persisted itinerary: %d days for trip %s", len(itinerary), trip_id[:8])
