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
2. A list of durable user preferences revealed (empty list if none).

Respond with JSON only, no prose:
{
  "episode": "...",
  "preferences": ["...", "..."]
}

Preferences must pass BOTH tests:

1. Concrete and reusable — e.g. "avoids overpriced tourist restaurants", "enjoys
   slow mornings in cafés". Omit vague entries.
2. Durable — still true on a completely different trip a year from now. Exclude
   anything tied to this specific trip: destinations, dates, durations, weather,
   or what the user did on a particular day.

Durable (include): "avoids overpriced tourist restaurants", "prefers early starts".
Transient (exclude): "visited Kyoto in April 2024", "traveled to Barcelona for 3 days",
"expects rainy season weather".

The episode summary is where trip-specific detail belongs — put it there, not in preferences."""


# Strong references to in-flight extraction tasks. asyncio only holds a weak
# reference to a running task, so a bare `create_task(...)` whose result nobody
# keeps can be garbage-collected mid-await and vanish without ever raising --
# the extraction simply never happens and nothing is logged. Journal entries
# seeded in bulk (scripts/seed.py posts N entries then exits) are the case where
# this bites: on the `egwene` profile, 12 journal entries produced 12 `journals`
# rows but 0 `journal-` episodes. See B-1 / B-4 in OPEN-ITEMS.md.
_extraction_tasks: set[asyncio.Task] = set()


def _spawn_extraction(entry_id: str, trip_destination: str, body: str) -> None:
    task = asyncio.create_task(_extract_journal_memory(entry_id, trip_destination, body))
    _extraction_tasks.add(task)
    task.add_done_callback(_extraction_tasks.discard)


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
            logger.warning("journal | extraction returned empty content for entry=%s", entry_id[:8])
            return
        extracted = json.loads(raw)
        episode = extracted.get("episode", "").strip()
        preferences = [p for p in extracted.get("preferences", []) if p.strip()]
        if episode:
            mem.store_episode(
                f"journal-{entry_id}", episode,
                source="journal", destination=trip_destination,
            )
        else:
            # Previously this returned quietly and the entry silently had no
            # episode. An entry that produces no episode is a prompt/model
            # problem worth seeing, not a normal outcome.
            logger.warning(
                "journal | extraction produced no episode for entry=%s (raw=%r)",
                entry_id[:8], raw[:200],
            )
        if preferences:
            mem.store_preferences(preferences, source="journal", destination=trip_destination)
        logger.info(
            "journal | memory extraction complete for entry=%s: %d episode, %d preferences",
            entry_id[:8], 1 if episode else 0, len(preferences),
        )
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
    _spawn_extraction(entry.id, trip.destination, entry.body)
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
    fields = body.model_dump(exclude_unset=True)
    for field, value in fields.items():
        setattr(entry, field, value)
    await session.commit()
    await session.refresh(entry)
    mem.store_journal_entry(entry.id, trip_id, trip.destination, entry.date, entry.body)
    if "body" in fields:
        # Re-extract when the text changed, or the episode keeps describing the
        # pre-edit entry. store_episode upserts on the same `journal-{id}` key,
        # so this replaces rather than duplicates. Derived *preferences* are not
        # revoked -- they have no back-reference to the entry that produced them
        # (B-2 in OPEN-ITEMS.md); this fixes the episode half only.
        _spawn_extraction(entry.id, trip.destination, entry.body)
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
