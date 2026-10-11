import os
from openai import AsyncOpenAI

# Default model — override via OPENROUTER_MODEL env var to switch providers/models
DEFAULT_MODEL = "openai/gpt-6-luna"

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        from app.usage import instrument_client  # local import to avoid cycle
        from app.tracing import instrument_client as instrument_tracing

        _client = instrument_tracing(
            instrument_client(
                AsyncOpenAI(
                    api_key=os.environ["OPENROUTER_API_KEY"],
                    base_url="https://openrouter.ai/api/v1",
                )
            )
        )
    return _client


def get_model() -> str:
    return os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)


def model_options(model: str) -> dict:
    """Return model-specific Chat Completions compatibility options."""
    if model == "openai/gpt-6-luna":
        # Luna only supports function calling through Chat Completions when
        # reasoning is disabled. Applying this to every Luna request also keeps
        # latency and token costs predictable across Voyager's LLM workloads.
        return {"reasoning_effort": "none"}
    return {}


async def llm_call(
    messages: list[dict],
    *,
    model: str | None = None,
    tools: list[dict] | None = None,
    tool_choice: str = "auto",
) -> object:
    """Thin wrapper around chat.completions.create with optional per-call model override."""
    selected_model = model or get_model()
    return await get_client().chat.completions.create(
        model=selected_model,
        messages=messages,
        **model_options(selected_model),
        **({"tools": tools, "tool_choice": tool_choice} if tools else {}),
    )
