from pydantic import BaseModel
from datetime import datetime
from typing import Any, Literal


class Message(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    trip_action: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class Conversation(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[Message] = []

    model_config = {"from_attributes": True}


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    content: str
    # Feature-flag override: which planner handles planning-intent messages.
    # None -> use VOYAGER_PLANNER env / default (see app.flags).
    planner: Literal["single", "multi"] | None = None
