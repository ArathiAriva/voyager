"""
Tool definitions and executors for the Voyager agent.

Each tool has:
  - A JSON schema (passed to the LLM so it knows what's available)
  - An executor function (called when the LLM invokes the tool)

To add a new tool: add its schema to TOOL_SCHEMAS and its executor to TOOL_EXECUTORS.
"""

import json
import logging
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
                        "enum": ["all", "past", "upcoming"],
                        "description": "Filter trips by status. Defaults to 'all'.",
                    }
                },
                "required": [],
            },
        },
    },
]

# ── Executors (called when the LLM fires a tool) ─────────────────────────────

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
                "destination": t.destination,
                "dates": t.dates,
                "status": t.status,
                "summary": t.summary,
            }
            for t in trips
        ]
    })


async def _execute_search_memory(args: dict, session: AsyncSession) -> str:
    query = args.get("query", "")
    results = memory.search_memory(query)
    if not results["episodes"] and not results["preferences"]:
        return json.dumps({"message": "No relevant memories found."})
    return json.dumps(results)


TOOL_EXECUTORS = {
    "get_trips": _execute_get_trips,
    "search_memory": _execute_search_memory,
}


async def execute_tool(name: str, args: dict, session: AsyncSession) -> str:
    executor = TOOL_EXECUTORS.get(name)
    if not executor:
        logger.warning("Unknown tool called: %s", name)
        return json.dumps({"error": f"Unknown tool: {name}"})
    logger.debug("Executing tool %s with args: %s", name, args)
    result = await executor(args, session)
    logger.debug("Tool %s result: %s", name, result)
    return result
