"""Usage/cost reporting endpoints."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.orm import UsageLogORM

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/summary")
async def usage_summary(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Totals plus breakdowns by model, context, and day for the last N days."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    base = select(
        func.count(UsageLogORM.id),
        func.coalesce(func.sum(UsageLogORM.prompt_tokens), 0),
        func.coalesce(func.sum(UsageLogORM.completion_tokens), 0),
        func.coalesce(func.sum(UsageLogORM.cost_usd), 0.0),
    ).where(UsageLogORM.created_at >= since)

    calls, prompt, completion, cost = (await session.execute(base)).one()

    async def breakdown(col):
        rows = await session.execute(
            select(
                col,
                func.count(UsageLogORM.id),
                func.coalesce(func.sum(UsageLogORM.total_tokens), 0),
                func.coalesce(func.sum(UsageLogORM.cost_usd), 0.0),
            )
            .where(UsageLogORM.created_at >= since)
            .group_by(col)
            .order_by(func.coalesce(func.sum(UsageLogORM.cost_usd), 0.0).desc())
        )
        return [
            {"key": k, "calls": c, "total_tokens": t, "cost_usd": round(cu, 6)}
            for k, c, t, cu in rows
        ]

    day = func.date(UsageLogORM.created_at)
    return {
        "window_days": days,
        "totals": {
            "calls": calls,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "cost_usd": round(cost, 6),
        },
        "by_model": await breakdown(UsageLogORM.model),
        "by_context": await breakdown(UsageLogORM.context),
        "by_day": await breakdown(day),
    }


@router.get("/recent")
async def recent_calls(
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = (
        await session.execute(
            select(UsageLogORM).order_by(UsageLogORM.created_at.desc()).limit(limit)
        )
    ).scalars()
    return [
        {
            "created_at": r.created_at.isoformat(),
            "model": r.model,
            "context": r.context,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "cost_usd": r.cost_usd,
        }
        for r in rows
    ]
