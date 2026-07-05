"""
Planning graph router — detects planning intent and invokes the LangGraph graph.
"""

import logging
from collections.abc import Callable, Coroutine
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.planning.graph import planning_graph
from app.planning.state import PlanningState

logger = logging.getLogger("voyager.planning.router")

_PLANNING_PHRASES = (
    "plan my", "plan a", "plan the",
    "itinerary", "day itinerary", "days in", "day trip",
    "week in", "schedule my", "schedule a",
    "organise my trip", "organize my trip",
    "arrange my trip", "build an itinerary",
)

_REVISION_PHRASES = (
    "redo the", "redo my", "revise the", "revise my",
    "find cheaper restaurants", "find better restaurants",
    "change day", "update the itinerary", "update my itinerary",
    "swap the", "replace the",
)

StepEmitter = Callable[[str], Coroutine[Any, Any, None]]


def is_planning_request(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _PLANNING_PHRASES + _REVISION_PHRASES)


async def run_planning_graph(
    user_message: str,
    session: AsyncSession,
    trip_id: str | None = None,
    emit_step: StepEmitter | None = None,
) -> str:
    """Invoke the planning graph and return the final reply string."""
    initial_state: PlanningState = {
        "user_message": user_message,
        "trip_id": trip_id,
        "revision_scope": {"domains": [], "day_range": None, "instruction": ""},
        "user_preferences": [],
        "saved_places": [],
        "past_trips": [],
        "existing_itinerary": None,
        "brief": {},
        "activities": [],
        "food": [],
        "logistics": [],
        "accommodation": [],
        "itinerary_draft": [],
        "unplaced_items": [],
        "conflicts": [],
        "critique_score": 5,
        "critique_issues": [],
        "revision_count": 0,
        "missing_info": [],
        "final_reply": "",
    }

    logger.info("planning | starting graph for message: %s", user_message[:80])

    final_state = await planning_graph.ainvoke(
        initial_state,
        config={"configurable": {"session": session, "emit_step": emit_step}},
    )

    reply = final_state.get("final_reply", "")
    if not reply:
        reply = "I've planned your trip! Check the Itinerary tab to see the full day-by-day plan."

    logger.info("planning | graph complete, critic_score=%d", final_state.get("critique_score", 0))
    return reply
