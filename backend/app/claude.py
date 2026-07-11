import os
from openai import AsyncOpenAI

# Default model — override via OPENROUTER_MODEL env var to switch providers/models
DEFAULT_MODEL = "anthropic/claude-haiku-4-5"

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        from app.usage import instrument_client  # local import to avoid cycle

        _client = instrument_client(
            AsyncOpenAI(
                api_key=os.environ["OPENROUTER_API_KEY"],
                base_url="https://openrouter.ai/api/v1",
            )
        )
    return _client


def get_model() -> str:
    return os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)


async def llm_call(
    messages: list[dict],
    *,
    model: str | None = None,
    tools: list[dict] | None = None,
    tool_choice: str = "auto",
) -> object:
    """Thin wrapper around chat.completions.create with optional per-call model override."""
    return await get_client().chat.completions.create(
        model=model or get_model(),
        messages=messages,
        **({"tools": tools, "tool_choice": tool_choice} if tools else {}),
    )
