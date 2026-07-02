"""
Logistics Researcher — transport, timing, and practical movement between areas.
No search_places needed; works from the activity list passed in state.
"""

import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.claude import llm_call
from app.planning.state import PlanningState
from app.agents import parse_json_response

logger = logging.getLogger("voyager.agents.logistics")

SYSTEM_PROMPT = """You are a logistics researcher for a travel planning system.
You receive a planning brief and the list of planned activities with their areas/neighbourhoods.
Your job is to surface transport notes, timing constraints, and practical movement advice.

Do NOT generate a full itinerary. Just provide logistics data the optimizer will use.

Return a JSON object — no prose, no code fences:
{
  "airport_transfer": "Notes on getting from airport to accommodation area",
  "local_transport": "Primary local transport mode (metro, walking, taxi, etc.) and tips",
  "intercity": [],  // [{from, to, mode, duration_hours, advance_booking_required, notes}]
  "area_travel_times": {},  // {"{area_a} to {area_b}": "~20 min by metro"}
  "timing_constraints": [],  // [{day_or_area, constraint, reason}]
  "advance_bookings": []  // [{item, reason, how_far_ahead}]
}

Focus on transitions between areas that appear in the activities list.
Flag anything that needs advance booking (Shinkansen, ferries, popular attractions)."""


async def run(state: PlanningState, session: AsyncSession, model: str | None = None) -> dict:
    brief = state["brief"]
    payload = {
        "brief": brief,
        "activities": state.get("activities", []),
    }

    response = await llm_call(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ],
        model=model,
    )
    try:
        result = parse_json_response(response.choices[0].message.content or "")
        logger.info("logistics | produced transport notes for %d areas", len(result.get("area_travel_times", {})))
        return {"logistics": [result]}
    except (ValueError, TypeError):
        logger.warning("logistics | failed to parse output: %s", (response.choices[0].message.content or "")[:200])
        return {"logistics": []}
