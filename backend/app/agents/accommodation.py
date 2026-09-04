"""
Accommodation Researcher — recommends hotels based on activity cluster areas.
Runs after activities and food researchers so it can pick the most central area.
"""

import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.claude import llm_call
from app.tools import tools_named, execute_tool
from app.planning.state import PlanningState
from app.agents import parse_json_response, scope_search_args

logger = logging.getLogger("voyager.agents.accommodation")

SYSTEM_PROMPT = """You are an accommodation researcher for a travel planning system.
You receive a planning brief AND the outputs from the activities and food researchers.
Your job is to recommend where the user should stay, optimised for convenience to their
planned activities and meals.

Use search_places to find saved hotels.

CRITICAL: You MUST respond with a valid JSON array and nothing else. No prose, no explanation,
no markdown, no code fences. Even if the user has no saved hotels, return a JSON array of
recommended accommodation options based on the activity areas in the brief.

Analyse the area distribution of activities and food — recommend accommodation in the
neighbourhood with the highest density of planned items.

[
  {
    "name": "Hotel/accommodation name",
    "area": "Neighbourhood/district",
    "price_tier": "budget | mid-range | luxury",
    "why_convenient": "Explanation of why this location works for the planned activities",
    "priority": "high | medium | low",
    "source": "saved | recommended"
  }
]

Prioritise saved places tagged as "hotel". Return 2-3 options."""

TOOLS = tools_named("search_places")


async def run(state: PlanningState, session: AsyncSession, model: str | None = None) -> dict:
    brief = state["brief"]
    payload = {
        "brief": brief,
        "activities": state.get("activities", []),
        "food": state.get("food", []),
    }

    history = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload)},
    ]

    for _ in range(3):
        response = await llm_call(history, model=model, tools=TOOLS)
        msg = response.choices[0].message

        if not msg.tool_calls:
            try:
                items = parse_json_response(msg.content or "")
                logger.info("accommodation | found %d options", len(items))
                return {"accommodation": items}
            except (ValueError, TypeError):
                logger.warning("accommodation | failed to parse output: %s", (msg.content or "")[:200])
                return {"accommodation": []}

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
                # force_category: this researcher only ever wants hotels, unlike
                # food/activities which let the model narrow within their domain.
                scope_search_args(args, brief, category="hotel", force_category=True)
            result = await execute_tool(tc.function.name, args, session)
            history.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    logger.warning("accommodation | exceeded tool loop iterations")
    return {"accommodation": []}
