"""
Planning graph router — detects planning intent and invokes the LangGraph graph.
"""

import itertools
import logging
import re
import time
from collections.abc import Callable, Coroutine
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.planning import trace as planning_trace
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

# A revision that misses this list falls through to the single-agent loop, which
# is the dangerous path: set_itinerary replaces the whole itinerary, so an edit
# there risks losing days. Measured against natural phrasings, the list above
# caught only 2 of 8 ("change day ...", "update the itinerary ..."); the rest --
# "make day 2 more relaxed", "do the museum on day 2 instead", "add a coffee stop
# on the second day" -- routed to chat.
#
# Rather than chase every verb, match the shape these requests share: a reference
# to a specific day of an itinerary. Requires BOTH a day reference and an edit
# verb, so "what did I do on day 2?" stays a question rather than triggering a
# replan.
_DAY_REFERENCE = re.compile(
    r"\b(day\s*\d+|"
    r"(?:first|second|third|fourth|fifth|sixth|seventh|last|final)\s+day|"
    r"morning|afternoon|evening)\b",
    re.IGNORECASE,
)
_EDIT_VERB = re.compile(
    r"\b(add|remove|drop|swap|replace|change|move|shift|make|adjust|tweak|"
    r"rearrange|reorder|instead|rather|more|less|skip|cut|extend|shorten)\b",
    re.IGNORECASE,
)

StepEmitter = Callable[[str], Coroutine[Any, Any, None]]


def is_planning_request(text: str) -> bool:
    lower = text.lower()
    if any(phrase in lower for phrase in _PLANNING_PHRASES + _REVISION_PHRASES):
        return True
    return bool(_DAY_REFERENCE.search(lower) and _EDIT_VERB.search(lower))


async def run_planning_graph(
    user_message: str,
    session: AsyncSession,
    trip_id: str | None = None,
    conversation_trip_id: str | None = None,
    emit_step: StepEmitter | None = None,
    conversation_id: str | None = None,
) -> str:
    """Invoke the planning graph and return the final reply string."""
    initial_state: PlanningState = {
        "user_message": user_message,
        "trip_id": trip_id,
        "conversation_trip_id": conversation_trip_id,
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

    # Trace the run so it can be inspected afterwards in the Planning tab.
    run_id = await planning_trace.start_run(conversation_id, user_message)
    started = time.perf_counter()

    try:
        final_state = await planning_graph.ainvoke(
            initial_state,
            config={"configurable": {
                "session": session,
                "emit_step": emit_step,
                "planning_run_id": run_id,
                "planning_seq": itertools.count(),
            }},
        )
    except Exception as e:
        await planning_trace.finish_run(
            run_id, status="failed", duration_ms=(time.perf_counter() - started) * 1000,
            error=str(e),
        )
        raise

    await planning_trace.finish_run(
        run_id, status="complete", final_state=final_state,
        duration_ms=(time.perf_counter() - started) * 1000,
    )

    reply = final_state.get("final_reply", "")
    if not reply:
        reply = "I've planned your trip! Check the Itinerary tab to see the full day-by-day plan."

    logger.info("planning | graph complete, critic_score=%d", final_state.get("critique_score", 0))
    return reply
