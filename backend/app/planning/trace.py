"""Persist multi-agent planning runs so they can be inspected after the fact.

The graph traced every LLM call to `trace_log.jsonl` (app/tracing.py), but that is
opt-in, unredacted, size-capped, and carries no run id — calls could only be grouped by
clustering timestamps, which breaks the moment two runs overlap. This records the run
itself: one row per run, one per node, with what each agent handed the next.

Written fail-open, like usage_log and retrieval_log: a trace failure must never break a
planning request.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("voyager.planning.trace")

#: Nodes whose state delta is large and uninteresting verbatim; the summary carries it.
_MAX_OUTPUT_CHARS = 20000


def _truncate(value: Any) -> Any:
    """Keep a step's stored output bounded without losing its shape."""
    try:
        import json

        encoded = json.dumps(value, default=str)
    except Exception:
        return {"_unserialisable": str(value)[:500]}
    if len(encoded) <= _MAX_OUTPUT_CHARS:
        import json

        return json.loads(encoded)
    return {"_truncated": True, "_preview": encoded[:_MAX_OUTPUT_CHARS]}


def summarise(node: str, delta: dict) -> str:
    """One line describing what a node produced, for the timeline.

    Node-aware because the interesting fact differs per agent: a researcher is judged
    by how many options it returned and where, the critic by its score.
    """
    try:
        if node == "classify_intent":
            bits = [f"intent={delta.get('brief', {}).get('intent') or delta.get('intent', '?')}"]
            dest = delta.get("brief", {}).get("destination")
            if dest:
                bits.append(dest)
            return " · ".join(str(b) for b in bits)

        if node == "build_brief":
            brief = delta.get("brief", {}) or {}
            parts = [p for p in (brief.get("destination"), brief.get("dates")) if p]
            days = brief.get("duration_days")
            if days:
                parts.append(f"{days} days")
            return " · ".join(str(p) for p in parts) or "brief built"

        if node == "load_context":
            return (
                f"{len(delta.get('user_preferences') or [])} preferences · "
                f"{len(delta.get('saved_places') or [])} saved places · "
                f"{len(delta.get('past_trips') or [])} past trips"
            )

        for key, noun in (("activities", "activities"), ("food", "food options"),
                          ("logistics", "logistics notes"), ("accommodation", "stays")):
            if key in delta:
                items = delta.get(key) or []
                areas = {i.get("area") for i in items if isinstance(i, dict) and i.get("area")}
                suffix = f" across {len(areas)} areas" if areas else ""
                return f"{len(items)} {noun}{suffix}"

        if node == "optimizer":
            days = delta.get("itinerary_draft") or []
            unplaced = delta.get("unplaced_items") or []
            tail = f" · {len(unplaced)} unplaced" if unplaced else ""
            return f"{len(days)} day(s) drafted{tail}"

        if node == "critic":
            issues = delta.get("critique_issues") or []
            return f"score {delta.get('critique_score', '?')}/5 · {len(issues)} issue(s)"

        if node == "assemble_reply":
            return f"{len(delta.get('final_reply') or '')} char reply"

        if node == "clarify":
            return f"{len(delta.get('missing_info') or [])} question(s) back to user"
    except Exception:
        pass
    return ", ".join(sorted(delta.keys())) if delta else ""


async def start_run(conversation_id: str | None, user_message: str) -> str | None:
    """Open a run row. Returns its id, or None if tracing failed (never raises)."""
    run_id = str(uuid.uuid4())
    try:
        from app.db import SessionLocal
        from app.models.orm import PlanningRunORM

        async with SessionLocal() as session:
            session.add(PlanningRunORM(
                id=run_id,
                created_at=datetime.now(timezone.utc),
                conversation_id=conversation_id,
                user_message=user_message[:4000],
                status="running",
            ))
            await session.commit()
        return run_id
    except Exception:
        logger.debug("planning trace | could not start run (non-fatal)", exc_info=True)
        return None


async def record_step(run_id: str | None, seq: int, node: str, label: str,
                      delta: dict, duration_ms: float, started_at: datetime,
                      error: str | None = None) -> None:
    if not run_id:
        return
    try:
        from app.db import SessionLocal
        from app.models.orm import PlanningStepORM

        async with SessionLocal() as session:
            session.add(PlanningStepORM(
                id=str(uuid.uuid4()),
                run_id=run_id,
                seq=seq,
                node=node,
                label=label,
                started_at=started_at,
                duration_ms=round(duration_ms, 2),
                summary=summarise(node, delta or {}),
                output=_truncate(delta or {}),
                error=error,
            ))
            await session.commit()
    except Exception:
        logger.debug("planning trace | could not record step %s (non-fatal)", node, exc_info=True)


async def finish_run(run_id: str | None, *, status: str, final_state: dict | None = None,
                     duration_ms: float | None = None, error: str | None = None) -> None:
    if not run_id:
        return
    try:
        from app.db import SessionLocal
        from app.models.orm import PlanningRunORM

        state = final_state or {}
        brief = state.get("brief") or {}
        async with SessionLocal() as session:
            run = await session.get(PlanningRunORM, run_id)
            if not run:
                return
            run.status = status
            run.destination = brief.get("destination")
            run.intent = brief.get("intent")
            run.critic_score = state.get("critique_score")
            run.revision_count = state.get("revision_count") or 0
            run.duration_ms = round(duration_ms, 2) if duration_ms is not None else None
            run.error = error
            await session.commit()
    except Exception:
        logger.debug("planning trace | could not finish run (non-fatal)", exc_info=True)
