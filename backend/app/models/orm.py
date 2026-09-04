from sqlalchemy import String, ForeignKey, Text, DateTime, JSON, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from app.db import Base


class TripORM(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    destination: Mapped[str] = mapped_column(String, nullable=False)
    dates: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    emoji: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(String, nullable=False, default="")
    cover_photo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, nullable=True, default=list)
    itinerary: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)

    journal_entries: Mapped[list["JournalEntryORM"]] = relationship(
        "JournalEntryORM", back_populates="trip", order_by="JournalEntryORM.date.desc()", cascade="all, delete-orphan"
    )
    connected_content: Mapped[list["ConnectedContentORM"]] = relationship(
        "ConnectedContentORM", back_populates="trip", order_by="ConnectedContentORM.created_at.desc()", cascade="all, delete-orphan"
    )
    saved_places: Mapped[list["SavedPlaceORM"]] = relationship(
        "SavedPlaceORM", back_populates="trip", order_by="SavedPlaceORM.created_at.desc()", cascade="all, delete-orphan"
    )


class JournalEntryORM(Base):
    __tablename__ = "journal_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    trip_id: Mapped[str] = mapped_column(String, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[str] = mapped_column(String, nullable=False)  # YYYY-MM-DD, the day of travel
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False, default="app")  # app | telegram | email
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    trip: Mapped["TripORM"] = relationship("TripORM", back_populates="journal_entries")


class ConnectedContentORM(Base):
    __tablename__ = "connected_content"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    trip_id: Mapped[str] = mapped_column(String, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False, default="other")  # album | instagram | tiktok | blog | other
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String, nullable=True)
    captured_at: Mapped[str | None] = mapped_column(String, nullable=True)  # ISO date when content was created
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    trip: Mapped["TripORM"] = relationship("TripORM", back_populates="connected_content")


class SavedPlaceORM(Base):
    __tablename__ = "saved_places"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    trip_id: Mapped[str] = mapped_column(String, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str] = mapped_column(String, nullable=False, default="other")
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    area: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String, nullable=True)
    enrichment_status: Mapped[str] = mapped_column(String, nullable=False, default="none")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    trip: Mapped["TripORM"] = relationship("TripORM", back_populates="saved_places")


class ConversationORM(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False, default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    messages: Mapped[list["MessageORM"]] = relationship("MessageORM", back_populates="conversation", order_by="MessageORM.created_at")


class MessageORM(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    conversation: Mapped["ConversationORM"] = relationship("ConversationORM", back_populates="messages")


class RetrievalLogORM(Base):
    """One row per vector-search call — the retrieval counterpart to `usage_log`.

    Voyager is a RAG app whose retrieval layer was entirely unmeasured: both eval
    suites judge the final reply, so they cannot separate "the retriever missed it"
    from "the LLM ignored it". Two silent retrieval failures (B-6, S-7) were found by
    accident reading tool-call logs. See docs/retrieval-quality-spec.md.
    """
    __tablename__ = "retrieval_log"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    #: saved_places / episodic / semantic / journals
    collection: Mapped[str] = mapped_column(String, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: filters actually applied (destination / trip_id / category), JSON object
    filters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    n_requested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_returned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: stable Chroma IDs, so a result stays auditable after the fact
    result_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    #: similarity scores; Chroma returns these on every query and they were discarded
    distances: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    #: usage_context + node_context, e.g. "planning:food_researcher"
    caller: Mapped[str] = mapped_column(String, nullable=False, default="unspecified")
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class UsageLogORM(Base):
    """One row per LLM API call — token counts and OpenRouter-reported cost."""
    __tablename__ = "usage_log"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    model: Mapped[str] = mapped_column(String, nullable=False)
    context: Mapped[str] = mapped_column(String, nullable=False, default="unspecified")
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
