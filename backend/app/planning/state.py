from typing import Annotated, Literal, TypedDict
from operator import add


class RevisionScope(TypedDict):
    domains: list[Literal["activities", "food", "accommodation", "logistics"]]
    day_range: tuple[int, int] | None  # None = whole trip; (3, 3) = Day 3 only
    instruction: str  # user's revision request in natural language


class PlanningState(TypedDict):
    # Input
    user_message: str
    trip_id: str | None  # resolved by Planner via get_trips
    #: The trip the *conversation* is scoped to, when the user set one. Distinct
    #: from `trip_id`: this is user intent, that is whatever the graph resolved.
    #: Used at persist time to avoid inventing a duplicate trip (B-13).
    conversation_trip_id: str | None

    # Execution mode
    revision_scope: RevisionScope

    # User context (loaded at start)
    user_preferences: list[str]
    saved_places: list[dict]
    past_trips: list[dict]

    # Existing itinerary from TripORM (None for fresh plans; populated for revisions)
    existing_itinerary: list[dict] | None

    # Planning brief built by Planner
    brief: dict

    # Researcher outputs — Annotated[list, add] so parallel fan-in appends rather than clobbers
    activities: Annotated[list[dict], add]
    food: Annotated[list[dict], add]
    logistics: Annotated[list[dict], add]
    accommodation: list[dict]  # runs sequentially after others; no reducer needed

    # Optimizer output
    itinerary_draft: list[dict]
    unplaced_items: list[str]
    conflicts: list[str]

    # Critic output
    critique_score: int
    critique_issues: list[dict]
    revision_count: int  # guard against infinite loops (max 2)

    # Clarification
    missing_info: list[str]  # fields the user hasn't provided yet (e.g. ["duration", "destination"])

    # Final output
    final_reply: str
