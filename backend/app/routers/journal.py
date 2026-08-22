import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.orm import TripORM, JournalEntryORM
from app.models.trip import JournalEntry, JournalEntryCreate, JournalEntryUpdate
from app.claude import get_client, get_model
from app import memory as mem

logger = logging.getLogger("voyager.journal")

router = APIRouter(prefix="/trips/{trip_id}/journal", tags=["journal"])

JOURNAL_EXTRACTION_PROMPT = """You are a memory extraction assistant for a travel journal app.
Given a travel journal entry, extract:
1. A one-sentence episode summary of what happened.
2. A list of specific user preferences or facts revealed (empty list if none).

Respond with JSON only, no prose:
{
  "episode": "...",
  "preferences": ["...", "..."]
}

Preferences should be concrete and reusable (e.g. "avoids overpriced tourist restaurants", "enjoys slow mornings in cafés"). Omit vague entries."""


async def _extract_journal_memory(entry_id: str, trip_destination: str, body: str) -> None:
    try:
        client = get_client()
        response = await client.chat.completions.create(
            model=get_model(),
            messages=[
                {"role": "system", "content": JOURNAL_EXTRACTION_PROMPT},
                {"role": "user", "content": f"Destination: {trip_destination}\n\nJournal entry:\n{body}"},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        if not raw:
            return
        extracted = json.loads(raw)
        episode = extracted.get("episode", "").strip()
        preferences = [p for p in extracted.get("preferences", []) if p.strip()]
        if episode:
            mem.store_episode(f"journal-{entry_id}", episode)
        if preferences:
            mem.store_preferences(preferences)
        logger.info("journal | memory extraction complete for entry=%s: 1 episode, %d preferences", entry_id[:8], len(preferences))
    except Exception:
        logger.exception("journal | memory extraction failed for entry=%s (non-fatal)", entry_id[:8])


async def _get_trip_or_404(trip_id: str, session: AsyncSession) -> TripORM:
    trip = await session.get(TripORM, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@router.get("", response_model=list[JournalEntry])
async def list_journal_entries(trip_id: str, session: AsyncSession = Depends(get_session)) -> list[JournalEntry]:
    await _get_trip_or_404(trip_id, session)
    result = await session.execute(
        select(JournalEntryORM)
        .where(JournalEntryORM.trip_id == trip_id)
        .order_by(JournalEntryORM.date.desc())
    )
    return result.scalars().all()


@router.post("", response_model=JournalEntry, status_code=201)
async def create_journal_entry(
    trip_id: str,
    body: JournalEntryCreate,
    session: AsyncSession = Depends(get_session),
) -> JournalEntry:
    trip = await _get_trip_or_404(trip_id, session)
    entry = JournalEntryORM(
        id=str(uuid.uuid4()),
        trip_id=trip_id,
        created_at=datetime.now(timezone.utc),
        **body.model_dump(),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    asyncio.create_task(_extract_journal_memory(entry.id, trip.destination, entry.body))
    mem.store_journal_entry(entry.id, trip_id, trip.destination, entry.date, entry.body)
    return entry


@router.patch("/{entry_id}", response_model=JournalEntry)
async def update_journal_entry(
    trip_id: str,
    entry_id: str,
    body: JournalEntryUpdate,
    session: AsyncSession = Depends(get_session),
) -> JournalEntry:
    trip = await _get_trip_or_404(trip_id, session)
    entry = await session.get(JournalEntryORM, entry_id)
    if not entry or entry.trip_id != trip_id:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    await session.commit()
    await session.refresh(entry)
    mem.store_journal_entry(entry.id, trip_id, trip.destination, entry.date, entry.body)
    return entry


@router.delete("/{entry_id}", status_code=204)
async def delete_journal_entry(
    trip_id: str,
    entry_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    await _get_trip_or_404(trip_id, session)
    entry = await session.get(JournalEntryORM, entry_id)
    if not entry or entry.trip_id != trip_id:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    mem.delete_journal_entry(entry_id)
    await session.delete(entry)
    await session.commit()
