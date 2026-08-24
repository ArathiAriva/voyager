import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.orm import ConversationORM, MessageORM
from app.models.conversation import Conversation, ConversationSummary, SendMessageRequest, Message
from app.claude import get_client, get_model
from app.tools import TOOL_SCHEMAS, execute_tool
from app.mcp_client import mcp_tool_schemas, call_mcp_tool
from app.flags import resolve_planner
from app.usage import usage_context
from app.planning.router import is_planning_request, run_planning_graph
from app import memory

logger = logging.getLogger("voyager.conversations")

router = APIRouter(prefix="/conversations", tags=["conversations"])

SYSTEM_PROMPT = (
    "You are Voyager, an AI travel companion. "
    "Help users plan trips, discover destinations, build itineraries, and get local tips. "
    "Be concise, warm, and enthusiastic about travel. "
    "\n\n"
    "TRIP MANAGEMENT:\n"
    "You can create and update trips in the user's Voyager profile using the create_trip and update_trip tools.\n"
    "- When the user discusses a specific trip they are planning or have taken, proactively offer to save it: "
    "ask once, naturally — e.g. 'Want me to save this as a trip in Voyager?'\n"
    "- NEVER call create_trip or update_trip without explicit user confirmation first.\n"
    "- When editing, call get_trips first to find the correct trip ID.\n"
    "- After creating or updating a trip, confirm it briefly: 'Done! I've saved [destination] to your trips.'\n"
    "\n"
    "You have access to the user's saved trips via the get_trips tool — use it whenever their "
    "travel history or upcoming plans would help you give a more personalised answer. "
    "You have access to real-time weather forecasts via the get_weather tool — use it whenever "
    "the user asks about weather, packing, or conditions at a destination. "
    "You have a memory of past conversations and learned user preferences via the search_memory "
    "tool — use it at the start of any conversation where knowing the user's travel style, "
    "past experiences, or preferences would improve your answer. "
    "You can search the user's personal travel journal via the search_journal tool — use it "
    "when they ask about specific experiences, meals, feelings, or places from a past trip. "
    "Pass the trip_id (from get_trips) to scope the search to a single trip. "
    "You can save specific places (restaurants, hotels, attractions, neighbourhoods) to a trip "
    "using the save_place tool, and search them with search_places — use search_places when "
    "building itineraries or when the user asks what they've bookmarked."
)

EXTRACTION_PROMPT = """You are a memory extraction assistant for a travel app.
Given a conversation, extract:
1. A one-sentence episode summary describing what happened in this conversation.
2. A list of durable user preferences revealed (empty list if none).

Respond with JSON only, no prose:
{
  "episode": "...",
  "preferences": ["...", "..."]
}

Preferences must pass BOTH tests:

1. Concrete and reusable — e.g. "prefers boutique hotels over chains", "dislikes
   overly touristy areas", "enjoys street food". Omit vague or uninformative entries.
2. Durable — still true on a completely different trip a year from now. Exclude
   anything tied to a current or planned trip: destinations, dates, durations,
   weather, or what the user is doing right now. Also exclude observations about
   the user's use of the app itself.

Durable (include): "travels on a tight budget", "prefers relaxed pacing over packed days".
Transient (exclude): "planning a 7-day trip", "currently in Rome", "traveling in November",
"expects rainy season weather", "uses saved places for trip planning".

The episode summary is where trip-specific detail belongs — put it there, not in preferences."""


# Strong references to in-flight extraction tasks, plus a concurrency bound.
#
# asyncio holds only a weak reference to a running task, so a bare
# `create_task(...)` whose result nobody keeps can be garbage-collected
# mid-await and vanish -- no exception, no log line, the extraction simply never
# happens. That is not theoretical: the identical pattern in journal.py was the
# root cause of B-1 (12 journal entries, 12 `journals` rows, 0 episodes, nothing
# in the logs to explain it).
#
# The semaphore is the other half of B-4: every chat exchange spawns one of
# these, each making an LLM call, and nothing previously bounded how many ran at
# once. Extraction is background work -- it should queue, not stampede.
_extraction_tasks: set[asyncio.Task] = set()
_EXTRACTION_CONCURRENCY = 4
_extraction_semaphore = asyncio.Semaphore(_EXTRACTION_CONCURRENCY)


def _spawn_extraction(conversation_id: str, history: list[dict]) -> None:
    """Start a background memory extraction, retaining a reference until it finishes."""
    task = asyncio.create_task(_extract_and_store_memory(conversation_id, history))
    _extraction_tasks.add(task)
    task.add_done_callback(_extraction_tasks.discard)


async def _extract_and_store_memory(conversation_id: str, history: list[dict]) -> None:
    """Background: extract episode + preferences from the conversation and store in Chroma.

    Spawn via `_spawn_extraction`, never `asyncio.create_task` directly -- see the
    note above on why a bare task can silently disappear.
    """
    async with _extraction_semaphore:
        await _run_extraction(conversation_id, history)


async def _run_extraction(conversation_id: str, history: list[dict]) -> None:
    try:
        usage_context.set("memory_extraction")
        client = get_client()
        transcript = "\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in history
            if isinstance(m.get("content"), str) and m["role"] in ("user", "assistant")
        )
        response = await client.chat.completions.create(
            model=get_model(),
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": transcript},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
        # Strip markdown code fences if the model wrapped the JSON
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        if not raw:
            logger.warning("conv=%s | memory extraction returned empty response", conversation_id[:8])
            return
        extracted = json.loads(raw)
        episode = extracted.get("episode", "").strip()
        preferences = [p for p in extracted.get("preferences", []) if p.strip()]
        if episode:
            memory.store_episode(conversation_id, episode)
        if preferences:
            memory.store_preferences(preferences)
        logger.info("conv=%s | memory extraction complete: 1 episode, %d preferences", conversation_id[:8], len(preferences))
    except Exception:
        logger.exception("conv=%s | memory extraction failed (non-fatal)", conversation_id[:8])


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(session: AsyncSession = Depends(get_session)) -> list[ConversationSummary]:
    result = await session.execute(
        select(ConversationORM).order_by(ConversationORM.updated_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=ConversationSummary, status_code=201)
async def create_conversation(session: AsyncSession = Depends(get_session)) -> ConversationSummary:
    now = datetime.now(timezone.utc)
    conversation = ConversationORM(id=str(uuid.uuid4()), title="New conversation", created_at=now, updated_at=now)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


@router.get("/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str, session: AsyncSession = Depends(get_session)) -> Conversation:
    result = await session.execute(
        select(ConversationORM)
        .where(ConversationORM.id == conversation_id)
        .options(selectinload(ConversationORM.messages))
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    result = await session.execute(
        select(ConversationORM)
        .where(ConversationORM.id == conversation_id)
        .options(selectinload(ConversationORM.messages))
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    now = datetime.now(timezone.utc)

    user_msg = MessageORM(
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        role="user",
        content=body.content,
        created_at=now,
    )
    session.add(user_msg)

    if not conversation.messages:
        conversation.title = body.content[:60] + ("…" if len(body.content) > 60 else "")

    history = [{"role": m.role, "content": m.content} for m in conversation.messages]
    history.append({"role": "user", "content": body.content})

    model = get_model()
    logger.info(
        "conv=%s | user message (%d chars) | history depth: %d | model: %s",
        conversation_id[:8], len(body.content), len(history), model,
    )

    async def generate() -> AsyncGenerator[str, None]:
        # Persist the user message before doing any async LLM work
        await session.commit()

        try:
            mcp_schemas = await mcp_tool_schemas()
        except Exception as e:
            logger.warning("conv=%s | MCP server unavailable: %s", conversation_id[:8], e)
            mcp_schemas = []

        mcp_tool_names = {s["function"]["name"] for s in mcp_schemas}
        all_tools = TOOL_SCHEMAS + mcp_schemas

        # ── Multi-agent planning path (feature-flagged, see app.flags) ────────
        planner_mode = resolve_planner(body.planner)
        if planner_mode == "multi" and is_planning_request(body.content):
            logger.info("conv=%s | routing to planning graph (planner=%s)", conversation_id[:8], planner_mode)

            step_queue: asyncio.Queue[str | None] = asyncio.Queue()

            async def enqueue_step(label: str) -> None:
                await step_queue.put(label)

            async def run_graph() -> str:
                usage_context.set("planning")
                try:
                    return await run_planning_graph(
                        body.content, session, emit_step=enqueue_step
                    )
                finally:
                    await step_queue.put(None)  # sentinel

            yield _sse("step", {"label": "Starting trip planning…"})

            graph_task = asyncio.create_task(run_graph())

            # Drain step events while the graph runs
            while True:
                label = await step_queue.get()
                if label is None:
                    break
                yield _sse("step", {"label": label})

            try:
                planning_reply = await graph_task
            except Exception as e:
                logger.exception("conv=%s | planning graph failed, falling back to standard loop: %s", conversation_id[:8], e)
                planning_reply = None

            if planning_reply is not None:
                reply_msg = MessageORM(
                    id=str(uuid.uuid4()),
                    conversation_id=conversation_id,
                    role="assistant",
                    content=planning_reply,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(reply_msg)
                conversation.updated_at = datetime.now(timezone.utc)
                await session.commit()
                await session.refresh(reply_msg)
                _spawn_extraction(
                    conversation_id, history + [{"role": "assistant", "content": planning_reply}]
                )
                from app.models.conversation import Message as MessageSchema
                msg_out = MessageSchema(
                    id=reply_msg.id, role=reply_msg.role,
                    content=reply_msg.content, created_at=reply_msg.created_at,
                    trip_action=None,
                )
                yield _sse("done", msg_out.model_dump(mode="json"))
                return

        # ── Standard agentic tool-call loop ──────────────────────────────────
        usage_context.set("chat")
        yield _sse("step", {"label": "Thinking…"})

        client = get_client()
        iteration = 0
        trip_action: dict | None = None
        msg = None

        try:
            while True:
                iteration += 1
                logger.debug("conv=%s | LLM call #%d", conversation_id[:8], iteration)

                response = await client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
                    tools=all_tools,
                    tool_choice="auto",
                )
                msg = response.choices[0].message
                usage = response.usage

                if not msg.tool_calls:
                    logger.info(
                        "conv=%s | final reply after %d LLM call(s) | tokens: %d in / %d out",
                        conversation_id[:8], iteration,
                        usage.prompt_tokens if usage else 0,
                        usage.completion_tokens if usage else 0,
                    )
                    break

                tool_names = [tc.function.name for tc in msg.tool_calls]
                logger.info("conv=%s | LLM call #%d → tool calls: %s", conversation_id[:8], iteration, tool_names)

                # Emit a step label for the tool(s) being called
                readable = {
                    "get_trips": "Looking up your trips…",
                    "get_weather": "Fetching weather forecast…",
                    "search_memory": "Searching your travel memory…",
                    "search_journal": "Reading your travel journal…",
                    "search_places": "Looking up saved places…",
                    "save_place": "Saving place…",
                    "create_trip": "Creating trip…",
                    "update_trip": "Updating trip…",
                }
                labels = list(dict.fromkeys(
                    readable.get(n, f"Using {n}…") for n in tool_names
                ))
                for label in labels:
                    yield _sse("step", {"label": label})

                history.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ],
                })

                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments or "{}")
                    if tc.function.name in mcp_tool_names:
                        tool_result = await call_mcp_tool(tc.function.name, args)
                    else:
                        tool_result = await execute_tool(tc.function.name, args, session)
                    if tc.function.name in ("create_trip", "update_trip"):
                        try:
                            parsed = json.loads(tool_result)
                            if "action" in parsed:
                                trip_action = parsed
                        except Exception:
                            pass
                    history.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    })

        except Exception as e:
            logger.exception("conv=%s | LLM error: %s", conversation_id[:8], e)
            yield _sse("error", {"detail": str(e)})
            return

        reply_content = msg.content or "" if msg else ""
        reply_msg = MessageORM(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="assistant",
            content=reply_content,
            created_at=datetime.now(timezone.utc),
        )
        session.add(reply_msg)
        conversation.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(reply_msg)

        _spawn_extraction(conversation_id, history)

        from app.models.conversation import Message as MessageSchema
        msg_out = MessageSchema(
            id=reply_msg.id,
            role=reply_msg.role,
            content=reply_msg.content,
            created_at=reply_msg.created_at,
            trip_action=trip_action,
        )
        yield _sse("done", msg_out.model_dump(mode="json"))

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, session: AsyncSession = Depends(get_session)) -> None:
    conversation = await session.get(ConversationORM, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await session.delete(conversation)
    await session.commit()
