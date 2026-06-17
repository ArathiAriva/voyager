import os
from openai import AsyncOpenAI

# Default model — override via OPENROUTER_MODEL env var to switch providers/models
DEFAULT_MODEL = "anthropic/claude-haiku-4-5"

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1",
        )
    return _client


def get_model() -> str:
    return os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
