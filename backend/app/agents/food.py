"""
Food & Drink Researcher — finds restaurants, cafes, bars, and market experiences.
"""

import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.claude import llm_call
from app.tools import tools_named, execute_tool
from app.planning.state import PlanningState
from app.agents import parse_json_response, scope_search_args

logger = logging.getLogger("voyager.agents.food")

SYSTEM_PROMPT = """You are a food and drink researcher for a travel planning system.
You receive a planning brief and return meal recommendations for the trip.

Use the search_places tool to find saved places tagged as "restaurant", "cafe", or "bar".

CRITICAL: You MUST respond with a valid JSON array and nothing else. No prose, no explanation,
no markdown, no code fences. Even if the user has no saved places, still return a JSON array
of recommended food options based on the brief and their stated preferences.

Always tag each recommendation with an area/neighbourhood so the optimizer can co-locate
meals with nearby activities.

[
  {
    "name": "Place name",
    "category": "restaurant | cafe | bar",
    "area": "Neighbourhood/district name",
    "meal_type": "breakfast | lunch | dinner | snack | any",
    "cuisine": "Japanese | Italian | etc.",
    "price_tier": "budget | mid-range | luxury",
    "notes": "Speciality dishes, atmosphere, practical tips",
    "reservation_required": false,
    "priority": "high | medium | low",
    "source": "saved | recommended"
  }
]

Prioritise saved places. Provide 2-3 options per meal slot per day. Flag reservation-required spots."""

TOOLS = tools_named("search_places")


async def run(state: PlanningState, session: AsyncSession, model: str | None = None) -> dict:
    brief = state["brief"]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(brief)},
    ]

    history = list(messages)
    for _ in range(3):
        response = await llm_call(history, model=model, tools=TOOLS)
        msg = response.choices[0].message

        if not msg.tool_calls:
            try:
                items = parse_json_response(msg.content or "")
                logger.info("food | found %d options", len(items))
                return {"food": items}
            except (ValueError, TypeError):
                logger.warning("food | failed to parse output: %s", (msg.content or "")[:200])
                return {"food": []}

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
            if tc.function.name == "search_places":
                scope_search_args(args, brief, category="restaurant")
            result = await execute_tool(tc.function.name, args, session)
            history.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    logger.warning("food | exceeded tool loop iterations")
    return {"food": []}
