from unittest.mock import AsyncMock, Mock

import pytest

from app import claude


def test_default_model_is_gpt_6_luna(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    assert claude.get_model() == "openai/gpt-6-luna"


def test_model_options_disable_luna_reasoning_only():
    assert claude.model_options("openai/gpt-6-luna") == {"reasoning_effort": "none"}
    assert claude.model_options("anthropic/claude-haiku-4-5") == {}


@pytest.mark.asyncio
async def test_llm_call_uses_luna_tool_compatibility_options(monkeypatch):
    create = AsyncMock(return_value=object())
    client = Mock()
    client.chat.completions.create = create
    monkeypatch.setattr(claude, "get_client", lambda: client)

    tools = [{"type": "function", "function": {"name": "lookup"}}]
    await claude.llm_call([{"role": "user", "content": "hello"}], tools=tools)

    create.assert_awaited_once_with(
        model="openai/gpt-6-luna",
        messages=[{"role": "user", "content": "hello"}],
        reasoning_effort="none",
        tools=tools,
        tool_choice="auto",
    )
