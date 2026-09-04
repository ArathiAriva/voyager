"""Always-on instrumentation for the vector-search layer.

Voyager is a RAG app whose retrieval was entirely unmeasured. Both eval suites judge
the *final reply*, so when a plan is bad they cannot distinguish "the retriever missed
the relevant place" from "the LLM ignored it" -- and those need opposite fixes. Two
silent retrieval failures (B-6, S-7) were found only by accident, reading tool-call
logs for unrelated reasons.

This records one `retrieval_log` row per search call, the same way `app/usage.py`
records one `usage_log` row per LLM call, and with the same rule: **fail open**. An
accounting failure must never break a user request.

See docs/retrieval-quality-spec.md for the metrics this enables (zero-result rate,
distance distributions, filter effectiveness, saturation) -- all computable from live
traffic with no labels and no LLM calls.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

logger = logging.getLogger("voyager.retrieval")

# Recording tasks are spawned from synchronous search functions, so nothing awaits
# them. Retain strong references until they finish -- a bare create_task can be
# garbage-collected mid-await and vanish silently (B-1/B-4/B-11).
_pending: set[asyncio.Task] = set()


def caller_label() -> str:
    """Best-effort description of what issued a search, e.g. `planning:food`.

    Reuses the contextvars that already exist for cost accounting and tracing rather
    than threading a new parameter through every call site.
    """
    try:
        from app.usage import usage_context

        context = usage_context.get()
    except Exception:
        context = "unspecified"

    try:
        from app.tracing import node_context

        node = node_context.get()
    except Exception:
        node = ""

    return f"{context}:{node}" if node else context


def record(
    *,
    collection: str,
    query: str,
    n_requested: int,
    result_ids: Sequence[str],
    distances: Sequence[float],
    latency_ms: float,
    filters: dict[str, Any] | None = None,
) -> None:
    """Record one retrieval call. Never raises.

    Safe to call from synchronous code: the DB write is scheduled onto the running
    event loop. With no loop running (a script, a test), the call is a no-op rather
    than an error -- instrumentation must not dictate how callers are structured.
    """
    try:
        row_values = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc),
            "collection": collection,
            "query": query or "",
            "filters": {k: v for k, v in (filters or {}).items() if v is not None},
            "n_requested": n_requested,
            "n_returned": len(result_ids),
            "result_ids": list(result_ids),
            "distances": [float(d) for d in distances],
            "caller": caller_label(),
            "latency_ms": round(latency_ms, 2),
        }
    except Exception:
        logger.debug("retrieval | could not build log row (non-fatal)", exc_info=True)
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    task = loop.create_task(_write(row_values))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def _write(row_values: dict[str, Any]) -> None:
    try:
        from app.db import SessionLocal
        from app.models.orm import RetrievalLogORM

        async with SessionLocal() as session:
            session.add(RetrievalLogORM(**row_values))
            await session.commit()
    except Exception:
        logger.debug("retrieval | log write failed (non-fatal)", exc_info=True)
