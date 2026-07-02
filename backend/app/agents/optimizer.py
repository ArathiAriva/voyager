"""
Geospatial Optimizer — clusters and sequences researcher outputs into a day-by-day itinerary.
Phase 1: neighbourhood-string clustering (no geocoding API needed).
Pure function node — uses LLM for sequencing logic since string-based clustering is fuzzy.
"""

import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.claude import llm_call
from app.planning.state import PlanningState
from app.agents import parse_json_response

logger = logging.getLogger("voyager.agents.optimizer")

SYSTEM_PROMPT = """You are a trip itinerary optimizer. You receive the outputs from activity,
food, accommodation, and logistics researchers and arrange them into a coherent day-by-day plan.

Your primary goal: minimize unnecessary cross-city travel. Group activities, lunch, and dinner
in the same neighbourhood/area each day wherever possible.

Rules:
1. Assign the top-priority accommodation option across all days
2. Sequence each day to minimise travel: morning activity area → nearby lunch → afternoon in same area → dinner nearby
3. Spread high-priority activities across different days; don't cluster everything on Day 1
4. Respect timing constraints and advance-booking flags from logistics
5. Leave some breathing room — not every hour needs to be filled
6. Note any items that couldn't be placed (not enough days, conflicting locations, etc.)
7. Note any geographic conflicts (two must-do activities that are far apart on the same day)

Return JSON only — no prose, no code fences:
{
  "days": [
    {
      "day": 1,
      "date": null,
      "title": "Short title",
      "area_focus": "Primary neighbourhood for this day",
      "accommodation": "Hotel name, area",
      "plan": "Prose description: morning → lunch → afternoon → dinner, with tips and logistics notes"
    }
  ],
  "unplaced_items": ["Item name — reason it wasn't placed"],
  "conflicts": ["Description of any geographic or timing conflicts flagged"]
}"""


async def run(state: PlanningState, session: AsyncSession, model: str | None = None) -> dict:
    brief = state["brief"]
    logistics = state.get("logistics", [])
    logistics_data = logistics[0] if logistics else {}

    payload = {
        "brief": brief,
        "activities": state.get("activities", []),
        "food": state.get("food", []),
        "accommodation": state.get("accommodation", []),
        "logistics": logistics_data,
        "existing_itinerary": state.get("existing_itinerary"),
        "revision_scope": state.get("revision_scope", {}),
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
        days = result.get("days", [])
        logger.info("optimizer | produced %d-day itinerary", len(days))
        return {
            "itinerary_draft": days,
            "unplaced_items": result.get("unplaced_items", []),
            "conflicts": result.get("conflicts", []),
        }
    except (ValueError, TypeError):
        logger.warning("optimizer | failed to parse output: %s", (response.choices[0].message.content or "")[:200])
        return {"itinerary_draft": [], "unplaced_items": [], "conflicts": []}
