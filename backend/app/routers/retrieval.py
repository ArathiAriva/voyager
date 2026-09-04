"""Retrieval quality reporting endpoints.

The counterpart to `usage.py`: where that answers "what did this cost", this answers
"is the retriever finding the right things". Every metric here is computed from
`retrieval_log` alone -- no labels, no LLM calls, so it is cheap enough to look at
constantly. See docs/retrieval-quality-spec.md.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.orm import RetrievalLogORM

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


def _percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile. Small samples here, so no interpolation."""
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 4)


@router.get("/summary")
async def retrieval_summary(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Per-collection retrieval health for the last N days.

    The headline numbers, and what each one means when it moves:

    - `zero_rate` — share of searches returning nothing. Rising on `saved_places`
      means scoping is too tight; on `semantic` it means memory is not being found.
    - `best_distance_p50/p90` — distance of the top hit. Drifting upward means
      retrieval is degrading, and is the trigger for memory hygiene (M-3/M-4).
    - `saturation_rate` — how often the result set hit the requested limit, i.e. the
      limit is choosing for you rather than relevance.
    - `filtered_zero_rate` — zero-result rate for filtered searches specifically.
      B-6's fix could over-correct into over-scoping and nothing else would say so.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (await session.execute(
        select(RetrievalLogORM).where(RetrievalLogORM.created_at >= since)
    )).scalars().all()

    by_collection: dict[str, list[RetrievalLogORM]] = {}
    for row in rows:
        by_collection.setdefault(row.collection, []).append(row)

    collections = {}
    for name, entries in sorted(by_collection.items()):
        total = len(entries)
        zero = sum(1 for e in entries if e.n_returned == 0)
        saturated = sum(1 for e in entries if e.n_requested and e.n_returned >= e.n_requested)
        filtered = [e for e in entries if e.filters]
        filtered_zero = sum(1 for e in filtered if e.n_returned == 0)
        best = [min(e.distances) for e in entries if e.distances]
        latencies = [e.latency_ms for e in entries]

        collections[name] = {
            "searches": total,
            "zero_rate": round(zero / total, 4) if total else 0.0,
            "saturation_rate": round(saturated / total, 4) if total else 0.0,
            "filtered_searches": len(filtered),
            "filtered_zero_rate": round(filtered_zero / len(filtered), 4) if filtered else None,
            "best_distance_p50": _percentile(best, 0.50),
            "best_distance_p90": _percentile(best, 0.90),
            "latency_ms_p50": _percentile(latencies, 0.50),
            "avg_returned": round(sum(e.n_returned for e in entries) / total, 2) if total else 0.0,
        }

    by_caller: dict[str, dict] = {}
    for row in rows:
        entry = by_caller.setdefault(row.caller, {"searches": 0, "zero": 0})
        entry["searches"] += 1
        if row.n_returned == 0:
            entry["zero"] += 1
    callers = {
        caller: {
            "searches": v["searches"],
            "zero_rate": round(v["zero"] / v["searches"], 4) if v["searches"] else 0.0,
        }
        for caller, v in sorted(by_caller.items(), key=lambda kv: -kv[1]["searches"])
    }

    return {
        "days": days,
        "total_searches": len(rows),
        "collections": collections,
        "callers": callers,
    }


@router.get("/recent")
async def recent_retrievals(
    limit: int = Query(50, ge=1, le=500),
    collection: str | None = Query(None),
    zero_only: bool = Query(False, description="Only searches that returned nothing."),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Recent retrieval calls, newest first — for eyeballing what a bad number means."""
    stmt = select(RetrievalLogORM).order_by(RetrievalLogORM.created_at.desc())
    if collection:
        stmt = stmt.where(RetrievalLogORM.collection == collection)
    if zero_only:
        stmt = stmt.where(RetrievalLogORM.n_returned == 0)
    rows = (await session.execute(stmt.limit(limit))).scalars().all()

    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat(),
            "collection": r.collection,
            "query": r.query,
            "filters": r.filters,
            "n_requested": r.n_requested,
            "n_returned": r.n_returned,
            "result_ids": r.result_ids,
            "best_distance": round(min(r.distances), 4) if r.distances else None,
            "caller": r.caller,
            "latency_ms": r.latency_ms,
        }
        for r in rows
    ]
