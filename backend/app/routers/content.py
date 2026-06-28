import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.orm import TripORM, ConnectedContentORM
from app.models.trip import ConnectedContent, ConnectedContentCreate
from app.utils import fetch_og_metadata

logger = logging.getLogger("voyager.content")

router = APIRouter(prefix="/trips/{trip_id}/content", tags=["content"])


async def _get_trip_or_404(trip_id: str, session: AsyncSession) -> TripORM:
    trip = await session.get(TripORM, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@router.get("", response_model=list[ConnectedContent])
async def list_content(trip_id: str, session: AsyncSession = Depends(get_session)) -> list[ConnectedContent]:
    await _get_trip_or_404(trip_id, session)
    result = await session.execute(
        select(ConnectedContentORM)
        .where(ConnectedContentORM.trip_id == trip_id)
        .order_by(ConnectedContentORM.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=ConnectedContent, status_code=201)
async def add_content(
    trip_id: str,
    body: ConnectedContentCreate,
    session: AsyncSession = Depends(get_session),
) -> ConnectedContent:
    await _get_trip_or_404(trip_id, session)
    title, thumbnail_url = await fetch_og_metadata(body.url)
    item = ConnectedContentORM(
        id=str(uuid.uuid4()),
        trip_id=trip_id,
        title=title,
        thumbnail_url=thumbnail_url,
        created_at=datetime.now(timezone.utc),
        **body.model_dump(),
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    logger.info("content | added %s for trip=%s title=%s", body.url, trip_id[:8], title)
    return item


@router.delete("/{content_id}", status_code=204)
async def delete_content(
    trip_id: str,
    content_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    await _get_trip_or_404(trip_id, session)
    item = await session.get(ConnectedContentORM, content_id)
    if not item or item.trip_id != trip_id:
        raise HTTPException(status_code=404, detail="Content not found")
    await session.delete(item)
    await session.commit()
