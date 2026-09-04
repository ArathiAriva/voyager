import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.claude import get_client, get_model
from app.db import SessionLocal, get_session
from app import memory
from app.models.orm import TripORM, SavedPlaceORM
from app.models.trip import SavedPlace, SavedPlaceCreate, SavedPlaceUpdate, coerce_category
from app.utils import fetch_og_metadata

logger = logging.getLogger("voyager.places")

router = APIRouter(prefix="/trips/{trip_id}/places", tags=["places"])

PLACE_EXTRACTION_PROMPT = """You are a travel data extraction assistant.
Given the markdown content of a webpage about a place (restaurant, hotel, neighbourhood, attraction, etc.),
extract structured information and respond with JSON only — no prose, no code fences.

{
  "name": "Official name of the place",
  "address": "Full street address if present, else null",
  "area": "Neighbourhood or district name (e.g. 'Shinjuku', 'Le Marais', 'Shoreditch'). Infer from address or context if not explicit. Null if unknown.",
  "category": "One of: restaurant, cafe, bar, street food, hotel, neighbourhood, attraction, shop, beach, other",
  "summary": "2-3 sentences describing what makes this place worth visiting. Focus on atmosphere, specialities, and practical details a traveller would want."
}

If a field is not present in the content, use null. The summary must be original prose, not copied verbatim."""

async def _get_trip_or_404(trip_id: str, session: AsyncSession) -> TripORM:
    trip = await session.get(TripORM, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


# Background enrichment tasks. The event loop only holds a weak reference to a bare
# `asyncio.create_task(...)`, so an unreferenced task can be garbage-collected mid-await
# and vanish with no exception and no log line -- the same defect that silently dropped
# memory extraction (see B-1/B-4). Keep a strong reference until each task finishes, and
# bound concurrency so a bulk import cannot fire unlimited outbound Jina fetches.
_enrichment_tasks: set[asyncio.Task] = set()
_ENRICHMENT_CONCURRENCY = 4
_enrichment_semaphore = asyncio.Semaphore(_ENRICHMENT_CONCURRENCY)


def spawn_enrichment(place_id: str, url: str, destination: str) -> None:
    """Start place enrichment in the background, retaining a reference until it finishes.

    Always use this instead of `asyncio.create_task(_enrich_place(...))` directly.
    """
    task = asyncio.create_task(_enrich_place(place_id, url, destination))
    _enrichment_tasks.add(task)
    task.add_done_callback(_enrichment_tasks.discard)


async def _enrich_place(place_id: str, url: str, destination: str) -> None:
    """Background task: fetch URL via Jina Reader, extract structured data with LLM, update DB.

    Spawn via `spawn_enrichment`, never `asyncio.create_task` directly -- see the note
    above on why a bare task can silently disappear.
    """
    async with _enrichment_semaphore:
        await _run_enrichment(place_id, url, destination)


async def _run_enrichment(place_id: str, url: str, destination: str) -> None:
    try:
        jina_url = f"https://r.jina.ai/{url}"
        headers = {"Accept": "text/markdown"}
        api_key = os.getenv("JINA_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(jina_url, headers=headers)
            resp.raise_for_status()
            markdown = resp.text[:8000]

        llm = get_client()
        completion = await llm.chat.completions.create(
            model=get_model(),
            messages=[
                {"role": "system", "content": PLACE_EXTRACTION_PROMPT},
                {"role": "user", "content": f"URL: {url}\n\nContent:\n{markdown}"},
            ],
        )
        raw = (completion.choices[0].message.content or "").strip()
        # Strip ```json fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        extracted = json.loads(raw.strip())

        async with SessionLocal() as session:
            place = await session.get(SavedPlaceORM, place_id)
            if not place:
                return
            if extracted.get("name"):
                place.name = extracted["name"]
            if extracted.get("address") and not place.address:
                place.address = extracted["address"]
            if extracted.get("area") and not place.area:
                place.area = extracted["area"]
            if extracted.get("category"):
                # B-7: the model returns free text here; coerce so the row stays
                # readable by the `list[SavedPlace]` response model.
                place.category = coerce_category(extracted["category"])
            if extracted.get("summary"):
                place.summary = extracted["summary"]
            place.enrichment_status = "done"
            await session.commit()
            await session.refresh(place)

        embed_text = place.summary or place.notes or place.name
        memory.store_saved_place(place_id, place.trip_id, destination, place.name, place.category, embed_text)
        logger.info("places | enrichment done for place=%s", place_id[:8])

    except httpx.HTTPStatusError as e:
        logger.warning("places | Jina fetch failed for place=%s status=%d", place_id[:8], e.response.status_code)
        await _set_enrichment_status(place_id, "failed")
    except Exception:
        logger.exception("places | enrichment failed for place=%s (non-fatal)", place_id[:8])
        await _set_enrichment_status(place_id, "failed")


async def _set_enrichment_status(place_id: str, status: str) -> None:
    try:
        async with SessionLocal() as session:
            place = await session.get(SavedPlaceORM, place_id)
            if place:
                place.enrichment_status = status
                await session.commit()
    except Exception:
        logger.exception("places | could not set enrichment_status for place=%s", place_id[:8])


@router.get("", response_model=list[SavedPlace])
async def list_places(trip_id: str, session: AsyncSession = Depends(get_session)) -> list[SavedPlace]:
    await _get_trip_or_404(trip_id, session)
    result = await session.execute(
        select(SavedPlaceORM)
        .where(SavedPlaceORM.trip_id == trip_id)
        .order_by(SavedPlaceORM.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=SavedPlace, status_code=201)
async def create_place(
    trip_id: str,
    body: SavedPlaceCreate,
    session: AsyncSession = Depends(get_session),
) -> SavedPlace:
    trip = await _get_trip_or_404(trip_id, session)

    thumbnail_url: str | None = None
    if body.url:
        _, thumbnail_url = await fetch_og_metadata(body.url)

    place = SavedPlaceORM(
        id=str(uuid.uuid4()),
        trip_id=trip_id,
        name=body.name,
        url=body.url,
        category=body.category,
        area=body.area,
        address=body.address,
        notes=body.notes,
        thumbnail_url=thumbnail_url,
        enrichment_status="pending" if body.url else "none",
        created_at=datetime.now(timezone.utc),
    )
    session.add(place)
    await session.commit()
    await session.refresh(place)

    embed_text = place.notes or place.name
    memory.store_saved_place(place.id, trip_id, trip.destination, place.name, place.category, embed_text)

    if body.url:
        spawn_enrichment(place.id, body.url, trip.destination)

    logger.info("places | created place=%s (%s) for trip=%s", place.id[:8], place.name, trip_id[:8])
    return place


@router.patch("/{place_id}", response_model=SavedPlace)
async def update_place(
    trip_id: str,
    place_id: str,
    body: SavedPlaceUpdate,
    session: AsyncSession = Depends(get_session),
) -> SavedPlace:
    trip = await _get_trip_or_404(trip_id, session)
    place = await session.get(SavedPlaceORM, place_id)
    if not place or place.trip_id != trip_id:
        raise HTTPException(status_code=404, detail="Place not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(place, field, value)
    await session.commit()
    await session.refresh(place)

    embed_text = place.summary or place.notes or place.name
    memory.store_saved_place(place.id, trip_id, trip.destination, place.name, place.category, embed_text)

    return place


@router.delete("/{place_id}", status_code=204)
async def delete_place(
    trip_id: str,
    place_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    await _get_trip_or_404(trip_id, session)
    place = await session.get(SavedPlaceORM, place_id)
    if not place or place.trip_id != trip_id:
        raise HTTPException(status_code=404, detail="Place not found")
    memory.delete_saved_place(place_id)
    await session.delete(place)
    await session.commit()
