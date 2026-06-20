import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.orm import TripORM, ConnectedContentORM
from app.models.trip import ConnectedContent, ConnectedContentCreate

logger = logging.getLogger("voyager.content")

router = APIRouter(prefix="/trips/{trip_id}/content", tags=["content"])


async def _fetch_og_metadata(url: str) -> tuple[str | None, str | None]:
    """Fetch Open Graph title and image from a URL. Returns (title, thumbnail_url)."""
    try:
        import httpx
        from html.parser import HTMLParser

        class OGParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.og_title: str | None = None
                self.og_image: str | None = None
                self.page_title: str | None = None
                self._in_title = False

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                if tag == "meta":
                    prop = attrs_dict.get("property", "")
                    if prop == "og:title":
                        self.og_title = attrs_dict.get("content")
                    elif prop == "og:image":
                        self.og_image = attrs_dict.get("content")
                elif tag == "title":
                    self._in_title = True

            def handle_data(self, data):
                if self._in_title and not self.page_title:
                    self.page_title = data.strip()

            def handle_endtag(self, tag):
                if tag == "title":
                    self._in_title = False

        async with httpx.AsyncClient(follow_redirects=True, timeout=5.0) as client:
            resp = await client.get(url, headers={"User-Agent": "Voyager/1.0 (link preview)"})
            resp.raise_for_status()
            # Only parse HTML responses
            if "text/html" not in resp.headers.get("content-type", ""):
                return None, None
            parser = OGParser()
            parser.feed(resp.text[:50_000])  # cap at 50KB to avoid huge pages
            title = parser.og_title or parser.page_title
            return title, parser.og_image
    except Exception as e:
        logger.warning("OG fetch failed for %s: %s", url, e)
        return None, None


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
    title, thumbnail_url = await _fetch_og_metadata(body.url)
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
