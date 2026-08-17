import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.orm import TripORM
from app.models.trip import Trip, TripCreate, TripUpdate
from app import memory

router = APIRouter(prefix="/trips", tags=["trips"])


@router.get("", response_model=list[Trip])
async def list_trips(session: AsyncSession = Depends(get_session)) -> list[Trip]:
    result = await session.execute(select(TripORM))
    return result.scalars().all()


@router.get("/{trip_id}", response_model=Trip)
async def get_trip(trip_id: str, session: AsyncSession = Depends(get_session)) -> Trip:
    trip = await session.get(TripORM, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@router.post("", response_model=Trip, status_code=201)
async def create_trip(body: TripCreate, session: AsyncSession = Depends(get_session)) -> Trip:
    trip = TripORM(id=str(uuid.uuid4()), **body.model_dump())
    session.add(trip)
    await session.commit()
    await session.refresh(trip)
    return trip


@router.patch("/{trip_id}", response_model=Trip)
async def update_trip(
    trip_id: str, body: TripUpdate, session: AsyncSession = Depends(get_session)
) -> Trip:
    trip = await session.get(TripORM, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(trip, field, value)
    await session.commit()
    await session.refresh(trip)
    return trip


@router.delete("/{trip_id}", status_code=204)
async def delete_trip(trip_id: str, session: AsyncSession = Depends(get_session)) -> None:
    result = await session.execute(
        select(TripORM)
        .where(TripORM.id == trip_id)
        .options(selectinload(TripORM.saved_places), selectinload(TripORM.journal_entries))
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    # SQL rows cascade-delete (cascade="all, delete-orphan"), but the Chroma
    # embeddings for this trip's saved places / journal entries do not --
    # they'd otherwise be orphaned forever and keep surfacing in unrelated
    # trips' semantic search results.
    for place in trip.saved_places:
        memory.delete_saved_place(place.id)
    for entry in trip.journal_entries:
        memory.delete_journal_entry(entry.id)
    await session.delete(trip)
    await session.commit()
