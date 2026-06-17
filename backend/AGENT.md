# Agent guide — Voyager backend

This file tells Claude Code and any AI agent how to work in this directory.

## What this service is

The Voyager backend is a FastAPI service that fronts Claude (via the Anthropic SDK) for an AI travel companion. It handles chat sessions, trip data, and will grow to include memory, RAG, tool-calling agents, and multi-agent orchestration over a 6-month build.

## Development commands

```bash
# Activate the venv (always required)
source .venv/bin/activate

# Start the dev server
uvicorn app.main:app --reload

# Install dependencies after adding to requirements.txt
pip install -r requirements.txt
```

## Key files

- `app/claude.py` — Anthropic client singleton. Import `get_client()` and `MODEL` from here; never instantiate `AsyncAnthropic` elsewhere.
- `app/main.py` — App factory. Add new routers here.
- `app/routers/chat.py` — Chat endpoint. Currently returns stub replies; real Claude calls come next.
- `app/routers/trips.py` — Trip list endpoint. In-memory stub; will be backed by Postgres.

## Conventions

- All Claude calls go through `app/claude.py`. Use `get_client()` (async) and `MODEL`.
- Default to `claude-opus-4-8` with `thinking={"type": "adaptive"}` and streaming for anything with large input/output.
- Routers live in `app/routers/`, models in `app/models/`. Keep them separate.
- Pydantic v2 is in use — use `model_validate`, `model_dump`, not v1 aliases.
- Async throughout: route handlers are `async def`, use `await` for all I/O.

## Phased roadmap (don't build ahead)

| Month | What's being added |
|-------|--------------------|
| 1 (now) | Real Claude chat, basic tool use (search, weather) |
| 2 | Trip memory, preference learning, semantic + episodic memory |
| 3 | Journal ingestion, RAG over personal travel notes |
| 4 | Multi-agent planning (LangGraph) |
| 5 | Evaluation layer (LangSmith) |
| 6 | Auth, caching, observability, production deploy |

Build only what the current month requires. Don't introduce LangGraph, Qdrant, or auth until their phase.

## Testing

No test suite yet. When tests are added, they should hit a real in-process FastAPI test client (`httpx.AsyncClient` + `ASGITransport`), not mock the database or Claude client at the unit level.
