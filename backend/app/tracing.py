"""Local LLM call tracing — full request/response capture for debugging and
safety-eval forensics (e.g. did an injected instruction survive a planner
node's summarization step?).

Enable with VOYAGER_TRACE_LLM=1 (set in backend/.env for local dev, so the
planner's intermediate outputs -- notably build_brief -- are queryable after
the fact via `python -m evals.trace_query`). Writes one JSON line per
non-streaming chat.completions.create call to VOYAGER_TRACE_PATH (default
./trace_log.jsonl), tagged with the usage_context label (chat / planning /
eval_judge / ...) so a run can be filtered to the node of interest. This is a
lightweight, always-available alternative to Phoenix (app.observability),
which needs a running collector; both can be on at once.

PRIVACY: entries contain full prompt and response bodies verbatim, with no
redaction -- every conversation, saved place, and journal excerpt that reaches
an LLM. Intended for local dev profiles. The file is gitignored, but treat it
as sensitive if the profile holds real data.

Recording is fail-open: a tracing error never breaks the LLM call. The file
rolls to a single `.1` backup past VOYAGER_TRACE_MAX_MB (default 50) so it
can't grow unbounded unnoticed; older data beyond that backup is discarded.
"""
import json
import logging
import os
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("voyager.tracing")

_ENABLED = os.environ.get("VOYAGER_TRACE_LLM") == "1"
_TRACE_PATH = Path(os.environ.get("VOYAGER_TRACE_PATH", "./trace_log.jsonl"))
_MAX_BYTES = int(float(os.environ.get("VOYAGER_TRACE_MAX_MB", "50")) * 1024 * 1024)

# Which planner/graph node issued the call (finer-grained than usage_context,
# which labels the whole request e.g. "planning"). Set by node functions that
# want to be distinguishable in the trace log; defaults to "" (unset).
node_context: ContextVar[str] = ContextVar("node_context", default="")


def instrument_client(client: Any) -> Any:
    """Wrap client.chat.completions.create with local trace logging. Idempotent.
    No-op unless VOYAGER_TRACE_LLM=1. Composes with app.usage.instrument_client
    (apply both; each wraps the other's `create`)."""
    if not _ENABLED:
        return client
    completions = client.chat.completions
    if getattr(completions, "_voyager_trace_wrapped", False):
        return client
    original_create = completions.create

    async def create_with_tracing(*args: Any, **kwargs: Any) -> Any:
        response = await original_create(*args, **kwargs)
        if not kwargs.get("stream"):
            try:
                _record(kwargs, response)
            except Exception:
                logger.exception("tracing | failed to record trace (non-fatal)")
        return response

    completions.create = create_with_tracing
    completions._voyager_trace_wrapped = True
    logger.info("tracing | client instrumented for local LLM tracing -> %s", _TRACE_PATH)
    return client


def _record(kwargs: dict, response: Any) -> None:
    from app.usage import usage_context

    choice = response.choices[0] if getattr(response, "choices", None) else None
    message = getattr(choice, "message", None)
    entry = {
        "id": str(uuid.uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "context": usage_context.get(),
        "node": node_context.get(),
        "model": kwargs.get("model", "?"),
        "messages": kwargs.get("messages", []),
        "output": getattr(message, "content", None) if message else None,
        "tool_calls": (
            [
                {"name": tc.function.name, "arguments": tc.function.arguments}
                for tc in message.tool_calls
            ]
            if message and getattr(message, "tool_calls", None)
            else None
        ),
    }
    _roll_if_oversized()
    with _TRACE_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _roll_if_oversized() -> None:
    """Move the trace to a single `.1` backup once it exceeds the size cap.
    Keeps at most 2 files; anything older is dropped."""
    try:
        if _TRACE_PATH.exists() and _TRACE_PATH.stat().st_size >= _MAX_BYTES:
            _TRACE_PATH.replace(_TRACE_PATH.with_suffix(_TRACE_PATH.suffix + ".1"))
            logger.info("tracing | rolled %s past %d bytes", _TRACE_PATH, _MAX_BYTES)
    except OSError:
        logger.exception("tracing | failed to roll trace file (non-fatal)")
