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

logger = logging.getLogger("voyager.conversations")

router = APIRouter(prefix="/conversations", tags=["conversations"])

SYSTEM_PROMPT = (
    "You are Voyager, an AI travel companion. "
    "Help users plan trips, discover destinations, build itineraries, and get local tips. "
    "Be concise, warm, and enthusiastic about travel. "
    "You have access to the user's saved trips via the get_trips tool — use it whenever their "
    "travel history or upcoming plans would help you give a more personalised answer. "
    "You have access to real-time weather forecasts via the get_weather tool — use it whenever "
    "the user asks about weather, packing, or conditions at a destination."
)


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
    return reply_msg


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, session: AsyncSession = Depends(get_session)) -> None:
    conversation = await session.get(ConversationORM, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await session.delete(conversation)
    await session.commit()
