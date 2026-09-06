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
├── live_trip.py       # Trip temporality: is a trip happening now, which day (see docs/live-trip-mode.md)
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

`TOOL_SCHEMAS` is a **list**; use `tool_by_name(name)` / `tools_named(*names)` for lookups. Executors: `create_trip`, `update_trip`, `get_trips`, `get_current_trip`, `set_itinerary`, `save_place`, `search_places`, `search_journal`, `search_memory`, plus MCP tools (`get_weather`, `get_exchange_rate`) proxied through `mcp_client.py`.

**Live Trip Mode** (`app/live_trip.py`, design doc
[docs/live-trip-mode.md](../docs/live-trip-mode.md)). While a trip is underway the
agent knows which trip, which day, and today's plan, so it need not ask which city
the user is in. Two surfaces: the `get_current_trip` tool, and a short block
prepended to the system prompt by `_live_trip_prompt` — added only when a trip is
actually live, so most conversations pay nothing.

Liveness is **derived on read, never stored**. `trips.status = "active"` is
user-declared intent and goes stale (a trip marked active in March is still active
in September); `find_live_trip` ignores it and compares dates instead.
`resolve_trip_window` takes the best available source: itinerary day dates → the
Stage-2 `start_date`/`end_date` columns (not yet added; read defensively so the
resolver will not need changing) → an explicit range parsed out of the free-text
`dates` field.

**The itinerary is the primary source, not `dates`.** Itinerary days already carry
ISO dates written by the planner, so any planned trip is live-capable with no
migration. The `dates` parser is deliberately narrow — it accepts only ranges
naming specific days, because month-only values like "April 2024" identify a month
rather than a window and would make a trip live for 30 days. Returning `None` is
normal and means live mode does not engage.

Known limitation: "today" is the server's local date (`live_trip.today()`), which
is correct for a single-user local app and wrong once deployed across timezones.

`GET /trips` and `GET /trips/{id}` return derived `is_live`, `live_day` and
`live_total_days` (`_with_liveness` in `routers/trips.py`) so the UI does not have
to read `status` to decide whether a trip is happening. The stored `status` is
returned unchanged next to them.

**Saved places carry a `visited` flag.** `saved_places.visited` / `visited_at`
(migration `c9d4e18a52b6`), toggled from the place card or its modal, and mirrored
into the Chroma metadata so `search_places` can filter on it — "where did I eat in
Rome" and "where *could* I eat in Rome" are different questions the store could not
previously tell apart. The flag must be passed on **every** `store_saved_place`
call, not just the one that sets it, since PATCH re-embeds the place. A boolean
rather than a status enum: "planned / visited / skipped" invites a third state
nobody maintains. See [docs/visited-places-and-anecdotes.md](../docs/visited-places-and-anecdotes.md).

**Conversations can be scoped to a trip.** `conversations.trip_id` (nullable) is set
at creation (`POST /api/conversations {"trip_id": ...}`) or later
(`PATCH /api/conversations/{id}`), and threaded to the planning graph as
`conversation_trip_id`. `_resolve_trip_id` uses it directly and **creates no trip** —
without it the graph had only a destination string and invented a duplicate whenever
its fuzzy match missed (B-13). NULL is permanent and legitimate: most chats are
unscoped, and those still resolve by destination as before. See
[docs/trip-scoped-chats.md](../docs/trip-scoped-chats.md).

Note `ondelete` is **decorative** throughout this schema — SQLite does not enforce
foreign keys without `PRAGMA foreign_keys=ON`, which the app does not set, so the
`CASCADE`s are SQLAlchemy relationship cascades. `delete_trip` therefore clears
`conversations.trip_id` explicitly rather than relying on `SET NULL`.

**Editing a trip.** `update_trip` patches metadata (`destination`, `dates`,
`status`, `emoji`, `summary`, `tags`) — only the fields passed. Itineraries are
separate: `set_itinerary` **replaces the whole itinerary**, so an edit must pass
back every day, not just the changed one.

That replace semantic is a data-loss hazard, and two guards exist because a tool
description is guidance rather than a guarantee:
- `get_trips` returns each trip's `itinerary`. It previously did not, so the model
  was editing blind — asked to change one day it could only regenerate all of them
  from conversational memory, or write the one day and delete the rest.
- `_execute_set_itinerary` **refuses** a call that would shrink an existing
  itinerary, returning an error that explains how to proceed. Growing and the
  first write are unaffected. A genuinely shorter trip needs `update_trip` on the
  dates first, after confirming with the user.

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
| `VOYAGER_PLANNER` | No | `single` or `multi` (see evals-ops.md). Settable per-server with `scripts/run.sh --planner`, which is applied after the profile file is sourced so it wins over a profile value. |
| `PHOENIX_COLLECTOR_ENDPOINT` | No | Enables tracing when set |
| `VOYAGER_SEED_DEMO_TRIPS` | No | `0`/`false`/`no`/`off` stops `main.py` seeding the three demo trips into an empty DB on boot. Default on. Set it on a profile kept deliberately bare — otherwise deleting every trip and restarting brings them back, since the seed fires whenever the trips table is empty. Set on `moiraine`. |
| `VOYAGER_MAX_RETRIEVAL_DISTANCE` | No | Global override for the vector-search distance floor. Per-collection defaults (semantic/episodic 1.30, journals 1.45, saved_places 1.75) are usually what you want — see memory.md. |
| `VOYAGER_MAX_RETRIEVAL_DISTANCE_<COLLECTION>` | No | Overrides one collection's floor, e.g. `..._SEMANTIC`. Wins over the global override. |
| `VOYAGER_PREFERENCE_DEDUPE_DISTANCE` | No | L2 distance under which an incoming preference is treated as a re-wording of an existing one and skipped. Default `0.55`; calibrated on all-MiniLM-L6-v2 — see memory.md. |
| `BRAVE_API_KEY` | No | Enables the `web_search` MCP tool; without it the tool returns a "not configured" message instead of failing. Passed through to the MCP subprocess explicitly by `mcp_client.py` — the SDK only inherits an allowlist. |
