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


class PlanningRunORM(Base):
    """One row per multi-agent planning run — the trace the Planning tab renders.

    The graph already traced every LLM call to `trace_log.jsonl` via app/tracing.py,
    but that is opt-in (VOYAGER_TRACE_LLM=1), unredacted, rolls over at 50MB, and has
    no run identifier — calls can only be grouped by clustering timestamps, which
    breaks as soon as two runs overlap. This table gives each run a real id.
    """
    __tablename__ = "planning_run"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    user_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    destination: Mapped[str | None] = mapped_column(String, nullable=True)
    #: running / complete / failed
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    intent: Mapped[str | None] = mapped_column(String, nullable=True)
    critic_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    steps: Mapped[list["PlanningStepORM"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="PlanningStepORM.seq"
    )


class PlanningStepORM(Base):
    """One row per graph node execution within a planning run.

    `summary` is what the timeline shows at a glance; `output` holds the node's full
    result for the expanded view. Both are captured at the node boundary, so what is
    recorded is what one agent actually handed the next.
    """
    __tablename__ = "planning_step"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("planning_run.id", ondelete="CASCADE"), nullable=False)
    #: execution order within the run
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    node: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    #: one-line description of what this node produced, for the timeline
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: the node's full state delta — what it handed to the next agent
    output: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped["PlanningRunORM"] = relationship(back_populates="steps")


class RetrievalLogORM(Base):
    """One row per vector-search call — the retrieval counterpart to `usage_log`.

    Voyager is a RAG app whose retrieval layer was entirely unmeasured: both eval
    suites judge the final reply, so they cannot separate "the retriever missed it"
    from "the LLM ignored it". Two silent retrieval failures (B-6, S-7) were found by
    accident reading tool-call logs. See docs/retrieval-quality-spec.md.
    """
    __tablename__ = "retrieval_log"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True, default=lambda: datetime.now(timezone.utc))
    #: saved_places / episodic / semantic / journals
    collection: Mapped[str] = mapped_column(String, nullable=False, index=True)
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
