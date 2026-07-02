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
from app import memory

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
                        "enum": ["restaurant", "cafe", "bar", "hotel", "neighbourhood", "attraction", "shop", "beach", "other"],
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
                "their saved spots. Optionally scope to one trip or one category."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for, e.g. 'great ramen' or 'boutique hotels'."},
                    "trip_id": {"type": "string", "description": "Optional: restrict to one trip."},
                    "category": {
                        "type": "string",
                        "enum": ["restaurant", "cafe", "bar", "hotel", "neighbourhood", "attraction", "shop", "beach", "other"],
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
                "and a plan describing activities, logistics, and recommendations for that day."
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
]

# ── Executors (called when the LLM fires a tool) ─────────────────────────────

async def _execute_create_trip(args: dict, session: AsyncSession) -> str:
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
    return json.dumps({
        "action": "trip_created",
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
    from app.routers.places import _enrich_place
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
        category=args.get("category", "other"),
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
        asyncio.create_task(_enrich_place(place.id, place.url, trip.destination))

    logger.info("Tool save_place: saved place=%s (%s) for trip=%s", place.id[:8], place.name, trip_id[:8])
    return json.dumps({"action": "place_saved", "place_id": place.id, "name": place.name})


async def _execute_search_places(args: dict, session: AsyncSession) -> str:
    hits = memory.search_saved_places(
        args["query"],
        trip_id=args.get("trip_id"),
        category=args.get("category"),
    )
    if not hits:
        return json.dumps({"message": "No saved places found matching that query."})
    return json.dumps({"results": hits})


async def _execute_set_itinerary(args: dict, session: AsyncSession) -> str:
    trip_id = args.get("trip_id")
    trip = await session.get(TripORM, trip_id)
    if not trip:
        return json.dumps({"error": f"Trip {trip_id} not found."})
    trip.itinerary = args.get("days", [])
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
            }
            for t in trips
        ]
    })


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
    return json.dumps(results)


TOOL_EXECUTORS = {
    "create_trip": _execute_create_trip,
    "update_trip": _execute_update_trip,
    "set_itinerary": _execute_set_itinerary,
    "save_place": _execute_save_place,
    "search_places": _execute_search_places,
    "get_trips": _execute_get_trips,
    "search_journal": _execute_search_journal,
    "search_memory": _execute_search_memory,
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
