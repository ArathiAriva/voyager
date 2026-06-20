from pydantic import BaseModel
from typing import Literal


class TripBase(BaseModel):
    destination: str
    dates: str
    status: Literal["past", "upcoming"]
    emoji: str
    summary: str = ""
    cover_photo_url: str | None = None
    tags: list[str] = []


class TripCreate(TripBase):
    pass


class TripUpdate(BaseModel):
    destination: str | None = None
    dates: str | None = None
    status: Literal["past", "upcoming"] | None = None
    emoji: str | None = None
    summary: str | None = None
    cover_photo_url: str | None = None
    tags: list[str] | None = None


class Trip(TripBase):
    id: str

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
