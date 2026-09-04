"""Planning-run trace endpoints — what each agent handed the next, per run.

Companion to the cost (`usage`) and retrieval (`retrieval`) developer views. The
multi-agent graph is the hardest part of the system to reason about from the outside:
a plan comes back and there is no way to see which researcher produced what, what the
critic objected to, or where the time went. These endpoints expose that.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models.orm import PlanningRunORM, PlanningStepORM

router = APIRouter(prefix="/planning", tags=["planning"])


@router.get("/runs")
async def list_runs(
    limit: int = Query(30, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Recent planning runs, newest first."""
    runs = (await session.execute(
        select(PlanningRunORM)
        .options(selectinload(PlanningRunORM.steps))
        .order_by(PlanningRunORM.created_at.desc())
        .limit(limit)
    )).scalars().all()

    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat(),
            "conversation_id": r.conversation_id,
            "user_message": r.user_message,
            "destination": r.destination,
            "intent": r.intent,
            "status": r.status,
            "critic_score": r.critic_score,
            "revision_count": r.revision_count,
            "duration_ms": r.duration_ms,
            "step_count": len(r.steps),
            "error": r.error,
        }
        for r in runs
    ]


@router.get("/runs/{run_id}")
async def get_run(run_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    """One run with its full per-agent timeline, in execution order."""
    run = (await session.execute(
        select(PlanningRunORM)
        .options(selectinload(PlanningRunORM.steps))
        .where(PlanningRunORM.id == run_id)
    )).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Planning run not found")

    return {
        "id": run.id,
        "created_at": run.created_at.isoformat(),
        "conversation_id": run.conversation_id,
        "user_message": run.user_message,
        "destination": run.destination,
        "intent": run.intent,
        "status": run.status,
        "critic_score": run.critic_score,
        "revision_count": run.revision_count,
        "duration_ms": run.duration_ms,
        "error": run.error,
        "steps": [
            {
                "seq": s.seq,
                "node": s.node,
                "summary": s.summary,
                "started_at": s.started_at.isoformat(),
                "duration_ms": s.duration_ms,
                "output": s.output,
                "error": s.error,
            }
            for s in sorted(run.steps, key=lambda s: s.seq)
        ],
    }
