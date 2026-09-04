# Backend — FastAPI service

Python 3.12 / FastAPI / SQLAlchemy (async) / Pydantic v2. Lives in `backend/`.

## Layout

```
backend/app/
├── main.py            # App factory: logging config, CORS, router registration, startup seed
├── claude.py          # OpenRouter client singleton (openai SDK). ALL LLM calls go through here.
├── usage.py           # Wraps the client once to log every call to usage_log (fail-open)
├── flags.py           # VOYAGER_PLANNER feature flag (env + per-request override)
├── db.py              # Async engine + SessionLocal (per-profile SQLite)
├── tools.py           # Tool schemas + executors for the single-agent loop (471 lines)
├── memory.py          # Chroma memory system (see memory.md)
├── mcp_client.py      # stdio client that spawns mcp-server/server.py on demand
├── observability.py   # Phoenix/OTel tracing setup (no-op without PHOENIX_COLLECTOR_ENDPOINT)
├── routers/           # trips, conversations, journal, content, memories, places, usage
├── planning/          # LangGraph graph (see planning.md)
├── agents/            # Specialist agent nodes (see planning.md)
└── models/            # orm.py (SQLAlchemy), trip.py + conversation.py (Pydantic)
```

## The chat loop

`routers/conversations.py` is the heart: `POST /api/conversations/{id}/messages` returns an SSE stream (`_sse()` helper). Inside `generate()`:

1. Planning intent check (`app.planning.router.is_planning_request`) → LangGraph path with step events streamed to the UI; falls back to the single-agent loop on graph failure.
2. Otherwise: standard tool-call loop — LLM call with `TOOL_SCHEMAS`, execute tools via `execute_tool(name, args, session)`, repeat until a text reply.
3. After the reply, `_extract_and_store_memory` runs as a background task (episodic summary + preference extraction into Chroma).

## Tools (`app/tools.py`)

`TOOL_SCHEMAS` is a **list**; use `tool_by_name(name)` / `tools_named(*names)` for lookups. Executors: `create_trip`, `update_trip`, `get_trips`, `set_itinerary`, `save_place`, `search_places`, `search_journal`, `search_memory`, plus MCP tools (`get_weather`, `get_exchange_rate`) proxied through `mcp_client.py`.

## Conventions

- Never instantiate an LLM client outside `app/claude.py`; import `get_client()` and `get_model()`.
- Routers in `app/routers/`, ORM in `app/models/orm.py`, Pydantic schemas in `app/models/*.py` — keep separate.
- Async throughout: `async def` handlers, `await` all I/O.
- Pydantic v2 idioms: `model_validate`, `model_dump`.
- Tests hit a real in-process ASGI client (`httpx.AsyncClient` + `ASGITransport`); don't mock the DB or LLM client at the unit level.

## Running

```bash
cd backend && source .venv/bin/activate
bash scripts/run.sh --profile rand    # standard: per-profile DB/env, serves :8060 (override with --port)
bash scripts/migrate.sh               # Alembic migrations with DB backup/auto-restore (see INC-001)
```

## Env vars (`backend/.env`)

| Variable | Required | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | |
| `OPENROUTER_MODEL` | No | Default `anthropic/claude-haiku-4-5` |
| `VOYAGER_PLANNER` | No | `single` or `multi` (see evals-ops.md) |
| `PHOENIX_COLLECTOR_ENDPOINT` | No | Enables tracing when set |
| `BRAVE_API_KEY` | No | Enables the `web_search` MCP tool; without it the tool returns a "not configured" message instead of failing. Passed through to the MCP subprocess explicitly by `mcp_client.py` — the SDK only inherits an allowlist. |
