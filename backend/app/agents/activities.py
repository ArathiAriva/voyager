"""
Activities Researcher — finds attractions, experiences, and things to do.
"""

import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.claude import llm_call
from app.tools import tools_named, execute_tool
from app.planning.state import PlanningState
from app.agents import parse_json_response

logger = logging.getLogger("voyager.agents.activities")

SYSTEM_PROMPT = """You are an activities researcher for a travel planning system.
You receive a planning brief and the user's saved places, and return a ranked list
of activity recommendations for the trip.

Use the search_places tool to find saved places tagged as "attraction" or "neighbourhood".

CRITICAL: You MUST respond with a valid JSON array and nothing else. No prose, no explanation,
no markdown, no code fences. Even if the user has no saved places, still return a JSON array
of recommended activities based on the brief.

[
  {
    "name": "Place name",
    "category": "attraction | neighbourhood | other",
    "area": "Neighbourhood/district name",
    "duration_hours": 2,
    "best_time": "morning | afternoon | evening | any",
    "notes": "Why it's worth visiting, practical tips",
    "booking_required": false,
    "priority": "high | medium | low",
    "source": "saved | recommended"
  }
]

Prioritise saved places first. Include at least one local/hidden gem.
Aim for 1.5x the number of days in activities so the optimizer has options."""

TOOLS = tools_named("search_places")


async def run(state: PlanningState, session: AsyncSession, model: str | None = None) -> dict:
    brief = state["brief"]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(brief)},
    ]

    # Tool call loop (researchers may call search_places once or twice)
    history = list(messages)
    for _ in range(3):
        response = await llm_call(history, model=model, tools=TOOLS)
        msg = response.choices[0].message

        if not msg.tool_calls:
            try:
                items = parse_json_response(msg.content or "")
                logger.info("activities | found %d items", len(items))
                return {"activities": items}
            except (ValueError, TypeError):
                logger.warning("activities | failed to parse output: %s", (msg.content or "")[:200])
                return {"activities": []}

        history.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            # Scope search_places to activity-relevant categories
            if tc.function.name == "search_places":
                args.setdefault("category", "attraction")
            # Scope retrieval to this trip's destination. The researchers have no
            # trip_id (a fresh plan's trip is created later, at persist time), so
            # destination is the only scope available -- without it a Rome plan
            # retrieves the user's saved Lisbon and Istanbul places too.
            if tc.function.name == "search_places" and brief.get("destination"):
                args.setdefault("destination", brief["destination"])
            result = await execute_tool(tc.function.name, args, session)
            history.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    logger.warning("activities | exceeded tool loop iterations")
    return {"activities": []}
