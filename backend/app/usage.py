"""Cost/token accounting.

Wraps the OpenRouter client's `chat.completions.create` (see app.claude) to:
  1. request OpenRouter usage accounting (`usage: {include: true}`), which
     returns the actual cost in USD credits on every response — no local
     price table to maintain;
  2. persist one usage_log row per LLM call (model, tokens, cost, context).

Recording is fail-open: an accounting error never breaks the LLM call.
Streaming calls (stream=True) are passed through unrecorded.

Call-site context (chat / planning / memory / eval_judge / ...) is set via a
contextvar so deeply nested agent code doesn't need to thread labels through.
"""
import logging
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("voyager.usage")

usage_context: ContextVar[str] = ContextVar("usage_context", default="unspecified")


def instrument_client(client: Any) -> Any:
    """Wrap client.chat.completions.create with usage recording. Idempotent."""
    completions = client.chat.completions
    if getattr(completions, "_voyager_usage_wrapped", False):
        return client
    original_create = completions.create

    async def create_with_accounting(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("stream"):
            return await original_create(*args, **kwargs)
        # Ask OpenRouter to include cost in the usage block
        extra_body = dict(kwargs.get("extra_body") or {})
        extra_body.setdefault("usage", {"include": True})
        kwargs["extra_body"] = extra_body

        response = await original_create(*args, **kwargs)
        try:
            await _record(kwargs.get("model", "?"), response)
        except Exception:
            logger.exception("usage | failed to record usage (non-fatal)")
        return response

    completions.create = create_with_accounting
    completions._voyager_usage_wrapped = True
    logger.info("usage | client instrumented for cost/token accounting")
    return client


async def _record(model: str, response: Any) -> None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    from app.db import SessionLocal
    from app.models.orm import UsageLogORM

    row = UsageLogORM(
        id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        model=getattr(response, "model", None) or model,
        context=usage_context.get(),
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        total_tokens=getattr(usage, "total_tokens", 0) or 0,
        cost_usd=getattr(usage, "cost", None),  # OpenRouter usage accounting
    )
    async with SessionLocal() as session:
        session.add(row)
        await session.commit()
    logger.debug(
        "usage | %s ctx=%s tokens=%d/%d cost=%s",
        row.model, row.context, row.prompt_tokens, row.completion_tokens, row.cost_usd,
    )
