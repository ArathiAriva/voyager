"""Feature flags.

PLANNER — which planning architecture handles planning-intent messages:
  "multi"  (default) — LangGraph multi-agent planning graph
  "single"           — legacy single-agent tool-call loop

Resolution order: per-request override > VOYAGER_PLANNER env > default.
The per-request override exists so the eval harness (and, later, the UI)
can compare both planners in the same process.
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
