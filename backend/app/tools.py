"""
Tool definitions and executors for the Voyager agent.

Each tool has:
  - A JSON schema (passed to the LLM so it knows what's available)
  - An executor function (called when the LLM invokes the tool)

To add a new tool: add its schema to TOOL_SCHEMAS and its executor to TOOL_EXECUTORS.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.orm import TripORM
from app.models.trip import PLACE_CATEGORIES, coerce_category
from app.utils import dest_matches
from app import memory
from app import live_trip

logger = logging.getLogger("voyager.tools")

# ── Schemas (sent to the LLM) ────────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": (
                "Search your memory of past conversations and learned user preferences. "
                "Use this whenever the user references their past experiences, travel style, "
                "likes/dislikes, or when personalising a recommendation would help. "
                "Returns relevant episodic memories (past conversation summaries) and "
                "semantic memories (distilled preferences)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for, e.g. 'user preferences for accommodation' or 'past trips to Asia'.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_trip",
            "description": (
                "Save a new trip to the user's Voyager profile. "
                "IMPORTANT: Always ask the user for confirmation before calling this tool. "
                "Only call it after the user has explicitly agreed to save the trip. "
                "Pick an appropriate travel emoji for the destination."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {
                        "type": "string",
                        "description": "The trip destination, e.g. 'Kyoto, Japan'.",
                    },
                    "dates": {
                        "type": "string",
                        "description": "Human-readable date range, e.g. 'April 10–17 2025' or 'Summer 2026'.",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["past", "upcoming", "active"],
                        "description": "Whether this is a past, upcoming, or currently active trip.",
                    },
                    "emoji": {
                        "type": "string",
                        "description": "A single emoji representing the destination or trip vibe.",
                    },
                    "summary": {
                        "type": "string",
                        "description": "A short 1-2 sentence description of the trip.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags, e.g. ['beach', 'solo', 'budget'].",
                    },
                },
                "required": ["destination", "dates", "status", "emoji"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_trip",
            "description": (
                "Update an existing trip in the user's Voyager profile. "
                "Call get_trips first to find the trip ID. "
                "IMPORTANT: Always confirm with the user before making changes. "
                "Only include fields that should change."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "trip_id": {
                        "type": "string",
                        "description": "The ID of the trip to update.",
                    },
                    "destination": {"type": "string"},
                    "dates": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["past", "upcoming", "active"],
                    },
                    "emoji": {"type": "string"},
                    "summary": {"type": "string"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["trip_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_journal",
            "description": (
                "Search the user's travel journal entries using semantic similarity. "
                "Use this when the user asks about specific experiences, feelings, meals, places, "
                "or anything they might have written about during a trip. "
                "Optionally scope the search to a single trip by providing its trip_id "
                "(get it from get_trips). Returns matching journal excerpts with dates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for, e.g. 'best meal' or 'felt overwhelmed by crowds'.",
                    },
                    "trip_id": {
                        "type": "string",
                        "description": "Optional trip ID to restrict the search to one trip.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_place",
            "description": (
                "Save a specific place (restaurant, hotel, neighbourhood, attraction, etc.) "
                "to one of the user's trips. Use this when the user mentions a place they want "
                "to remember or visit. Call get_trips first to find the trip_id. "
                "If the user provides a URL, include it — the app will automatically enrich it. "
                "Otherwise save with a name and notes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "trip_id": {"type": "string", "description": "ID of the trip to attach this place to."},
                    "name": {"type": "string", "description": "Name of the place, e.g. 'Ichiran Ramen Shinjuku'."},
                    "url": {"type": "string", "description": "URL for the place (website, Google Maps, blog post). Always include this if you have it — the app uses it to fetch a thumbnail image and enrich the place details automatically."},
                    "category": {
                        "type": "string",
                        "enum": list(PLACE_CATEGORIES),
                    },
                    "area": {"type": "string", "description": "Neighbourhood or district name (e.g. 'Shinjuku', 'Le Marais'). Used for clustering places geographically."},
                    "address": {"type": "string", "description": "Street address if known."},
                    "notes": {"type": "string", "description": "Why this place is interesting or worth visiting."},
                },
                "required": ["trip_id", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_places",
            "description": (
                "Search the user's saved places semantically. Use this when the user asks about "
                "places they've bookmarked, or when building an itinerary and you want to incorporate "
                "their saved spots. ALWAYS pass `destination` when you are working on a specific "
                "trip or city -- saved places span every trip the user has taken, so an unscoped "
                "search returns restaurants from other countries. Optionally also scope to one "
                "trip or one category."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for, e.g. 'great ramen' or 'boutique hotels'."},
                    "trip_id": {"type": "string", "description": "Optional: restrict to one trip."},
                    "destination": {"type": "string", "description": "Optional: restrict to places saved for one destination, e.g. 'Rome' or 'Rome, Italy'."},
                    "category": {
                        "type": "string",
                        "enum": list(PLACE_CATEGORIES),
                        "description": "Optional: filter by place type.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_itinerary",
            "description": (
                "Save a day-by-day itinerary for a trip. "
                "Use this after planning an upcoming or active trip with the user. "
                "Call get_trips first to find the trip ID. "
                "Each day should have a day number, optional date (YYYY-MM-DD), optional title, "
                "and a plan describing activities, logistics, and recommendations for that day. "
                "REPLACES the entire itinerary — any day you omit is deleted. "
                "To change one day, call get_trips first, then pass back every existing day "
                "with only that day modified. Never call this with a single day unless the "
                "trip is genuinely one day long."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "trip_id": {
                        "type": "string",
                        "description": "The ID of the trip to attach the itinerary to.",
                    },
                    "days": {
                        "type": "array",
                        "description": "Ordered list of days in the itinerary.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "day": {"type": "integer", "description": "Day number, starting from 1."},
                                "date": {"type": "string", "description": "Date in YYYY-MM-DD format, if known."},
                                "title": {"type": "string", "description": "Short title for the day, e.g. 'Arrival & Arashiyama'."},
                                "plan": {"type": "string", "description": "Activities, places, logistics, and tips for this day."},
                                "area_focus": {"type": "string", "description": "Primary neighbourhood or district for this day, e.g. 'Arashiyama'. Used by the optimizer to cluster nearby food/places."},
                                "accommodation": {"type": "string", "description": "Where the user is staying this night, e.g. 'The Screen Kyoto, Nakagyo'."},
                            },
                            "required": ["day", "plan"],
                        },
                    },
                },
                "required": ["trip_id", "days"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trips",
            "description": (
                "Retrieve the user's saved trips from their Voyager profile. "
                "Returns past and upcoming trips with destination, dates, status, and a short summary. "
                "Call this whenever the user asks about their trips, travel history, or upcoming plans, "
                "or when their trips would help you give a more personalised answer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["all", "past", "upcoming", "active"],
                        "description": "Filter trips by status. Defaults to 'all'.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_trip",
            "description": (
                "Check whether the user is on a trip right now, and if so which day they are on "
                "and what today's plan says. Call this when a question depends on where the user "
                "is or what day it is — 'where should I eat', 'what's next', 'is it going to rain', "
                "'what should I do today'. Returns live: false when no trip is underway, in which "
                "case answer normally. Prefer this over asking the user which trip they mean."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

# ── Executors (called when the LLM fires a tool) ─────────────────────────────

def _trip_payload(trip: TripORM) -> dict:
    return {
        "id": trip.id,
        "destination": trip.destination,
        "dates": trip.dates,
        "status": trip.status,
        "emoji": trip.emoji,
        "summary": trip.summary,
        "tags": trip.tags,
    }


async def _execute_create_trip(args: dict, session: AsyncSession) -> str:
    # B-10: the model re-calls create_trip when asked "did you save it?", which used to
    # insert a second row. The prompt tells it to check get_trips first, but the guard
    # cannot live only there -- return the existing trip instead of duplicating it.
    # The planner's persist step already does this via dest_matches; this brings the
    # tool path in line.
    destination = args["destination"]
    dates = (args.get("dates") or "").strip().lower()
    existing = (await session.execute(select(TripORM))).scalars().all()
    for candidate in existing:
        if not dest_matches(candidate.destination, destination):
            continue
        if dates and (candidate.dates or "").strip().lower() != dates:
            continue
        logger.info(
            "Tool create_trip: matched existing trip %s (%s) -- not creating a duplicate",
            candidate.id[:8], candidate.destination,
        )
        return json.dumps({
            "action": "trip_already_exists",
            "note": (
                "A matching trip is already saved. Tell the user it is already there "
                "rather than saving again; use update_trip to change it."
            ),
            "trip": _trip_payload(candidate),
        })

    trip = TripORM(
        id=str(uuid.uuid4()),
        destination=args["destination"],
        dates=args["dates"],
        status=args["status"],
        emoji=args.get("emoji", "🧭"),
        summary=args.get("summary", ""),
        tags=args.get("tags", []),
    )
    session.add(trip)
    await session.commit()
    await session.refresh(trip)
    logger.info("Tool create_trip: created trip %s (%s)", trip.id[:8], trip.destination)
    return json.dumps({"action": "trip_created", "trip": _trip_payload(trip)})


async def _execute_update_trip(args: dict, session: AsyncSession) -> str:
    trip_id = args.get("trip_id")
    trip = await session.get(TripORM, trip_id)
    if not trip:
        return json.dumps({"error": f"Trip {trip_id} not found."})
    updatable = ("destination", "dates", "status", "emoji", "summary", "tags")
    for field in updatable:
        if field in args:
            setattr(trip, field, args[field])
    await session.commit()
    await session.refresh(trip)
    logger.info("Tool update_trip: updated trip %s (%s)", trip.id[:8], trip.destination)
    return json.dumps({
        "action": "trip_updated",
        "trip": {
            "id": trip.id,
            "destination": trip.destination,
            "dates": trip.dates,
            "status": trip.status,
            "emoji": trip.emoji,
            "summary": trip.summary,
            "tags": trip.tags,
        },
    })


async def _execute_save_place(args: dict, session: AsyncSession) -> str:
    import asyncio
    from app.models.orm import SavedPlaceORM
    from app.routers.places import spawn_enrichment
    from app.utils import fetch_og_metadata
    from datetime import datetime, timezone

    trip_id = args.get("trip_id")
    trip = await session.get(TripORM, trip_id)
    if not trip:
        return json.dumps({"error": f"Trip {trip_id} not found."})

    url = args.get("url")
    is_maps_url = url and "maps.google.com" in url
    thumbnail_url: str | None = None
    if url and not is_maps_url:
        _, thumbnail_url = await fetch_og_metadata(url)

    place = SavedPlaceORM(
        id=str(uuid.uuid4()),
        trip_id=trip_id,
        name=args["name"],
        url=url,
        category=coerce_category(args.get("category")),
        area=args.get("area"),
        address=args.get("address"),
        notes=args.get("notes"),
        thumbnail_url=thumbnail_url,
        enrichment_status="none" if (not url or is_maps_url) else "pending",
        created_at=datetime.now(timezone.utc),
    )
    session.add(place)
    await session.commit()
    await session.refresh(place)

    embed_text = place.notes or place.name
    memory.store_saved_place(place.id, trip_id, trip.destination, place.name, place.category, embed_text)

    if place.url and not is_maps_url:
        spawn_enrichment(place.id, place.url, trip.destination)

    logger.info("Tool save_place: saved place=%s (%s) for trip=%s", place.id[:8], place.name, trip_id[:8])
    return json.dumps({"action": "place_saved", "place_id": place.id, "name": place.name})


async def _execute_search_places(args: dict, session: AsyncSession) -> str:
    # `query` is schema-required, but models do omit it -- observed calling with
    # only {"destination": "Porto"}. A missing arg must not 500 the whole
    # conversation (KeyError propagated out of the tool loop and killed the
    # turn), so fall back to a broad match and let the destination/category
    # filters do the scoping.
    query = (args.get("query") or "").strip() or "saved places"
    hits = memory.search_saved_places(
        query,
        trip_id=args.get("trip_id"),
        category=args.get("category"),
        destination=args.get("destination"),
    )
    if not hits:
        return json.dumps({"message": "No saved places found matching that query."})
    return json.dumps({"results": hits})


async def _execute_set_itinerary(args: dict, session: AsyncSession) -> str:
    trip_id = args.get("trip_id")
    trip = await session.get(TripORM, trip_id)
    if not trip:
        return json.dumps({"error": f"Trip {trip_id} not found."})
    days = args.get("days", [])
    existing = trip.itinerary or []
    # Guard against the silent-truncation case: this tool replaces the whole
    # itinerary, so a model asked to "change day 3" that passes back only day 3
    # would delete the other days. The description warns about it, but a prompt is
    # guidance, not a guarantee -- and the loss is unrecoverable and invisible.
    # Shrinking is legitimate when deliberate (a trip genuinely got shorter), so
    # this refuses rather than silently merging, and tells the model how to proceed.
    if existing and len(days) < len(existing):
        submitted = sorted(d.get("day") for d in days if d.get("day") is not None)
        logger.warning(
            "Tool set_itinerary: refused truncation for trip %s (%d existing days, %d submitted: %s)",
            trip.id[:8], len(existing), len(days), submitted,
        )
        return json.dumps({
            "error": (
                f"This would replace a {len(existing)}-day itinerary with {len(days)} day(s), "
                f"deleting the rest. set_itinerary replaces the entire itinerary. "
                f"Pass back all {len(existing)} days with only the ones you mean to change "
                f"modified. If the trip really is now {len(days)} day(s) long, confirm with "
                f"the user first, then call update_trip to change the dates before retrying."
            ),
            "existing_days": len(existing),
            "submitted_days": len(days),
        })
    trip.itinerary = days
    await session.commit()
    await session.refresh(trip)
    logger.info("Tool set_itinerary: saved %d days for trip %s (%s)", len(trip.itinerary), trip.id[:8], trip.destination)
    return json.dumps({
        "action": "itinerary_saved",
        "trip_id": trip.id,
        "days": len(trip.itinerary),
    })


async def _execute_get_trips(args: dict, session: AsyncSession) -> str:
    status_filter = args.get("status", "all")
    query = select(TripORM)
    if status_filter in ("past", "upcoming"):
        query = query.where(TripORM.status == status_filter)
    result = await session.execute(query)
    trips = result.scalars().all()
    if not trips:
        return json.dumps({"trips": [], "message": "No trips found."})
    return json.dumps({
        "trips": [
            {
                "id": t.id,
                "destination": t.destination,
                "dates": t.dates,
                "status": t.status,
                "summary": t.summary,
                # The itinerary is included because set_itinerary replaces the whole
                # thing. Without it the model was editing blind: asked to change one
                # day it could only regenerate every day from conversational memory,
                # or write the single changed day and silently destroy the rest.
                "itinerary": t.itinerary,
            }
            for t in trips
        ]
    })


async def find_live_trip(session: AsyncSession) -> dict | None:
    """The trip the user is on today, with day number and today's plan, or None.

    Shared by the `get_current_trip` tool and the system-prompt injection so both
    answer from the same logic. Liveness is derived, never read from
    `trips.status` -- see app/live_trip.py for why.
    """
    result = await session.execute(select(TripORM))
    trips = result.scalars().all()
    now = live_trip.today()

    candidates: list[tuple[TripORM, live_trip.TripWindow]] = []
    for trip in trips:
        window = live_trip.resolve_trip_window(
            itinerary=trip.itinerary,
            dates=trip.dates,
            start_date=getattr(trip, "start_date", None),
            end_date=getattr(trip, "end_date", None),
        )
        if window and window.contains(now):
            candidates.append((trip, window))

    if not candidates:
        return None
    # Overlapping trips are possible. Prefer the one that started most recently
    # rather than silently picking whichever the DB returned first, and report
    # the ambiguity so the model can ask instead of assuming.
    candidates.sort(key=lambda pair: pair[1].start, reverse=True)
    trip, window = candidates[0]
    day_number = window.day_number(now)

    today_plan = None
    remaining: list[dict] = []
    for entry in (trip.itinerary or []):
        if not isinstance(entry, dict):
            continue
        if entry.get("date") and str(entry["date"])[:10] == now.isoformat():
            today_plan = entry
        elif entry.get("date") and str(entry["date"])[:10] > now.isoformat():
            remaining.append({"day": entry.get("day"), "date": entry.get("date"),
                              "title": entry.get("title")})
        elif not entry.get("date") and entry.get("day") == day_number:
            # Itinerary without dates: fall back to positional day matching.
            today_plan = entry

    return {
        "live": True,
        "trip_id": trip.id,
        "destination": trip.destination,
        "day_number": day_number,
        "total_days": window.total_days,
        "date": now.isoformat(),
        "window": {"start": window.start.isoformat(), "end": window.end.isoformat(),
                   "source": window.source},
        "today": today_plan,
        "remaining_days": remaining,
        "other_live_trips": [t.destination for t, _ in candidates[1:]],
    }


async def _execute_get_current_trip(args: dict, session: AsyncSession) -> str:
    live = await find_live_trip(session)
    if live is None:
        return json.dumps({
            "live": False,
            "message": ("The user is not on a trip today. Answer normally; do not assume "
                        "a destination."),
        })
    logger.info("Tool get_current_trip: day %s/%s of %s",
                live["day_number"], live["total_days"], live["destination"])
    return json.dumps(live)


async def _execute_search_journal(args: dict, session: AsyncSession) -> str:
    query = args.get("query", "")
    trip_id = args.get("trip_id")
    hits = memory.search_journals(query, trip_id=trip_id)
    if not hits:
        return json.dumps({"message": "No matching journal entries found."})
    return json.dumps({"results": hits})


async def _execute_search_memory(args: dict, session: AsyncSession) -> str:
    query = args.get("query", "")
    results = memory.search_memory(query)
    if not results["episodes"] and not results["preferences"]:
        return json.dumps({"message": "No relevant memories found."})
    # search_memory also returns id/distance hits for instrumentation; the model only
    # needs the documents, so don't spend context on them.
    return json.dumps({
        "episodes": results["episodes"],
        "preferences": results["preferences"],
    })


TOOL_EXECUTORS = {
    "create_trip": _execute_create_trip,
    "update_trip": _execute_update_trip,
    "set_itinerary": _execute_set_itinerary,
    "save_place": _execute_save_place,
    "search_places": _execute_search_places,
    "get_trips": _execute_get_trips,
    "search_journal": _execute_search_journal,
    "search_memory": _execute_search_memory,
    "get_current_trip": _execute_get_current_trip,
}


def tool_by_name(name: str) -> dict:
    """Return the tool schema for a given tool name. Raises KeyError if not found."""
    for t in TOOL_SCHEMAS:
        if t["function"]["name"] == name:
            return t
    raise KeyError(f"Tool not found: {name}")


def tools_named(*names: str) -> list[dict]:
    """Return a subset of TOOL_SCHEMAS matching the given names, preserving order."""
    return [tool_by_name(n) for n in names]


async def execute_tool(name: str, args: dict, session: AsyncSession) -> str:
    executor = TOOL_EXECUTORS.get(name)
    if not executor:
        logger.warning("Unknown tool called: %s", name)
        return json.dumps({"error": f"Unknown tool: {name}"})
    logger.debug("Executing tool %s with args: %s", name, args)
    result = await executor(args, session)
    logger.debug("Tool %s result: %s", name, result)
    return result
