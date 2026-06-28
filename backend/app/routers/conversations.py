import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.orm import ConversationORM, MessageORM
from app.models.conversation import Conversation, ConversationSummary, SendMessageRequest, Message
from app.claude import get_client, get_model
from app.tools import TOOL_SCHEMAS, execute_tool
from app.mcp_client import mcp_tool_schemas, call_mcp_tool
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
2. A list of specific user preferences or facts revealed (empty list if none).

Respond with JSON only, no prose:
{
  "episode": "...",
  "preferences": ["...", "..."]
}

Preferences should be concrete and reusable (e.g. "prefers boutique hotels over chains", "dislikes overly touristy areas", "enjoys street food"). Omit vague or uninformative entries."""


async def _extract_and_store_memory(conversation_id: str, history: list[dict]) -> None:
    """Fire-and-forget: extract episode + preferences from the conversation and store in Chroma."""
    try:
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


@router.post("/{conversation_id}/messages", response_model=Message)
async def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    session: AsyncSession = Depends(get_session),
) -> Message:
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

    # Auto-title after the first user message
    if not conversation.messages:
        conversation.title = body.content[:60] + ("…" if len(body.content) > 60 else "")

    history = [{"role": m.role, "content": m.content} for m in conversation.messages]
    history.append({"role": "user", "content": body.content})

    model = get_model()
    logger.info(
        "conv=%s | user message (%d chars) | history depth: %d | model: %s",
        conversation_id[:8], len(body.content), len(history), model,
    )

    try:
        mcp_schemas = await mcp_tool_schemas()
    except Exception as e:
        logger.warning("conv=%s | MCP server unavailable, continuing without MCP tools: %s", conversation_id[:8], e)
        mcp_schemas = []

    # Names served by MCP — used to route tool calls at execution time
    mcp_tool_names = {s["function"]["name"] for s in mcp_schemas}
    all_tools = TOOL_SCHEMAS + mcp_schemas

    client = get_client()
    iteration = 0
    trip_action: dict | None = None  # set if create_trip / update_trip fires
    # Agentic tool-call loop: keep going until the model returns a plain text reply
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

            # No tool calls — we have the final reply
            if not msg.tool_calls:
                logger.info(
                    "conv=%s | final reply after %d LLM call(s) | tokens: %d in / %d out",
                    conversation_id[:8], iteration,
                    usage.prompt_tokens if usage else 0,
                    usage.completion_tokens if usage else 0,
                )
                break

            tool_names = [tc.function.name for tc in msg.tool_calls]
            logger.info(
                "conv=%s | LLM call #%d → tool calls: %s",
                conversation_id[:8], iteration, tool_names,
            )

            # Append the assistant's tool-call turn to history
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

            # Execute each tool and append results
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                if tc.function.name in mcp_tool_names:
                    result = await call_mcp_tool(tc.function.name, args)
                else:
                    result = await execute_tool(tc.function.name, args, session)
                # Capture trip create/update actions for the frontend
                if tc.function.name in ("create_trip", "update_trip"):
                    try:
                        parsed = json.loads(result)
                        if "action" in parsed:
                            trip_action = parsed
                    except Exception:
                        pass
                history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

    except Exception as e:
        logger.exception("conv=%s | LLM error: %s", conversation_id[:8], e)
        raise HTTPException(status_code=502, detail=str(e))

    reply_content = msg.content or ""
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

    # Extract memories in the background — non-blocking, failures are logged not raised
    asyncio.create_task(_extract_and_store_memory(conversation_id, history))

    from app.models.conversation import Message as MessageSchema
    return MessageSchema(
        id=reply_msg.id,
        role=reply_msg.role,
        content=reply_msg.content,
        created_at=reply_msg.created_at,
        trip_action=trip_action,
    )


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, session: AsyncSession = Depends(get_session)) -> None:
    conversation = await session.get(ConversationORM, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await session.delete(conversation)
    await session.commit()
