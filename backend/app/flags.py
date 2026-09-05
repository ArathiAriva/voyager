"""Feature flags.

PLANNER — which planning architecture handles planning-intent messages:
  "multi"  (default) — LangGraph multi-agent planning graph
  "single"           — legacy single-agent tool-call loop

Resolution order: per-request override > VOYAGER_PLANNER env > default.
The per-request override exists so the eval harness (and, later, the UI)
can compare both planners in the same process.

SEED_DEMO_TRIPS — whether an empty database gets the three demo trips on boot.
  Set VOYAGER_SEED_DEMO_TRIPS=0 in a profile to keep it deliberately bare.
"""
import logging
import os
from typing import Literal

logger = logging.getLogger("voyager.flags")

PlannerMode = Literal["single", "multi"]

_VALID: tuple[PlannerMode, ...] = ("single", "multi")
DEFAULT_PLANNER: PlannerMode = "multi"


def resolve_planner(override: str | None = None) -> PlannerMode:
    for source, value in (("request", override), ("env", os.environ.get("VOYAGER_PLANNER"))):
        if value:
            value = value.lower()
            if value in _VALID:
                return value  # type: ignore[return-value]
            logger.warning("flags | invalid planner %r from %s; ignoring", value, source)
    return DEFAULT_PLANNER


# Values that mean "off". Anything else (including unset) leaves seeding on, so
# existing profiles keep the behaviour they have today.
_FALSEY = {"0", "false", "no", "off"}


def seed_demo_trips() -> bool:
    """Whether to insert the demo trips into an empty database on startup.

    Seeding fires only when the trips table is empty, which makes a deliberately
    bare profile impossible to keep across a restart: delete every trip, restart,
    and the demo trips return. That is fine for a fresh dev profile and wrong for
    one being used to test real behaviour from a clean slate, so profiles can opt
    out with VOYAGER_SEED_DEMO_TRIPS=0.
    """
    return os.environ.get("VOYAGER_SEED_DEMO_TRIPS", "1").strip().lower() not in _FALSEY
