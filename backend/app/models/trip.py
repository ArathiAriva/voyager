import logging
from datetime import datetime
from pydantic import BaseModel, field_validator
from typing import Literal, get_args

logger = logging.getLogger("voyager.models.trip")


class ItineraryDay(BaseModel):
    day: int
    date: str | None = None  # ISO "2025-04-10"; see the validator below
    title: str = ""
    plan: str  # freeform markdown or prose for the day
    area_focus: str | None = None  # primary neighbourhood/area for the day
    accommodation: str | None = None  # where the user is staying this day

    @field_validator("date")
    @classmethod
    def _normalise_date(cls, value: str | None) -> str | None:
        """Coerce a day's date to ISO, or drop it.

        The tool schema asks for YYYY-MM-DD but the field accepted any string, so
        nothing enforced it -- the planner wrote "September 4, 2026" on one run and
        ISO on another. Two things break on that: the UI renders
        `new Date(date + "T00:00:00")`, which yields "Invalid Date", and
        `live_trip._from_itinerary` cannot resolve a window, so Live Trip Mode
        loses today's plan.

        Normalising here fixes both at the boundary rather than teaching every
        reader to re-parse. An unparseable date becomes None, which every consumer
        already handles, instead of a string that silently poisons them.
        """
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y",
                    "%B %d %Y", "%b %d %Y", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        # ISO with a time component ("2026-09-04T00:00:00") is common enough to keep.
        try:
            return datetime.fromisoformat(text).date().isoformat()
        except ValueError:
            logger.warning("itinerary | dropping unparseable day date %r", text[:40])
            return None


class TripBase(BaseModel):
    destination: str
    dates: str
    status: Literal["past", "upcoming", "active"]
    emoji: str
    summary: str = ""
    cover_photo_url: str | None = None
    tags: list[str] = []
    itinerary: list[ItineraryDay] | None = None


class TripCreate(TripBase):
    pass


class TripUpdate(BaseModel):
    destination: str | None = None
    dates: str | None = None
    status: Literal["past", "upcoming", "active"] | None = None
    emoji: str | None = None
    summary: str | None = None
    cover_photo_url: str | None = None
    tags: list[str] | None = None
    itinerary: list[ItineraryDay] | None = None


class Trip(TripBase):
    id: str

    # Derived on read, never stored -- see app/live_trip.py and
    # docs/live-trip-mode.md. `status` stays the user's declared intent; these say
    # whether the trip is actually happening today. Storing liveness would need a
    # scheduler and would go stale exactly the way `status = "active"` does.
    is_live: bool = False
    live_day: int | None = None
    live_total_days: int | None = None

    model_config = {"from_attributes": True}


# ── Journal entries ──────────────────────────────────────────────────────────

class JournalEntryBase(BaseModel):
    date: str  # YYYY-MM-DD
    body: str
    source: Literal["app", "telegram", "email"] = "app"


class JournalEntryCreate(JournalEntryBase):
    pass


class JournalEntryUpdate(BaseModel):
    date: str | None = None
    body: str | None = None


class JournalEntry(JournalEntryBase):
    id: str
    trip_id: str

    model_config = {"from_attributes": True}


# ── Connected content ────────────────────────────────────────────────────────

class ConnectedContentBase(BaseModel):
    url: str
    type: Literal["album", "instagram", "tiktok", "blog", "other"] = "other"
    captured_at: str | None = None  # ISO date the content was originally created


class ConnectedContentCreate(ConnectedContentBase):
    pass


class ConnectedContent(ConnectedContentBase):
    id: str
    trip_id: str
    title: str | None = None
    thumbnail_url: str | None = None

    model_config = {"from_attributes": True}


# ── Saved places ─────────────────────────────────────────────────────────────

PlaceCategory = Literal[
    "restaurant", "cafe", "bar", "street food", "hotel",
    "neighbourhood", "attraction", "shop", "beach", "other",
]

#: The single source of truth for valid categories. The read path validates against
#: PlaceCategory, so any write path that bypasses it can persist a row the API cannot
#: serialise -- that mismatch was B-7. Use `coerce_category` on unvalidated input.
PLACE_CATEGORIES: tuple[str, ...] = get_args(PlaceCategory)


def coerce_category(value: str | None) -> str:
    """Map free-text category input onto the enum, falling back to 'other'.

    LLM-extracted and tool-supplied categories are not schema-checked, so they can be
    anything ('street food', 'Restaurant', 'ramen shop'). Coercing on write keeps the
    table readable by the response model.
    """
    if not value:
        return "other"
    normalised = value.strip().lower().replace("_", " ")
    if normalised in PLACE_CATEGORIES:
        return normalised
    return "other"


class SavedPlaceBase(BaseModel):
    name: str
    url: str | None = None
    category: PlaceCategory = "other"
    area: str | None = None
    address: str | None = None
    notes: str | None = None


class SavedPlaceCreate(SavedPlaceBase):
    pass


class SavedPlaceUpdate(BaseModel):
    name: str | None = None
    category: PlaceCategory | None = None
    area: str | None = None
    address: str | None = None
    notes: str | None = None
    summary: str | None = None


class SavedPlace(SavedPlaceBase):
    id: str
    trip_id: str
    summary: str | None = None
    thumbnail_url: str | None = None
    enrichment_status: Literal["none", "pending", "done", "failed"] = "none"
    created_at: datetime

    model_config = {"from_attributes": True}
