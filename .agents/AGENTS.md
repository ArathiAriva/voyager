# Voyager — Agent Context

Voyager is an AI travel companion (chat, trip planning, memory, journal RAG) built as a 6-month AI-engineering learning project. Currently at Month 4.5 of 6: single-agent chat loop + LangGraph multi-agent planner are both live, feature-flagged for A/B evals.

## System at a glance

```
Next.js 16 UI (:3000) ──HTTP/SSE──▶ FastAPI backend (:8060)
                                      ├─ Single-agent chat loop (tool calling)
                                      ├─ LangGraph planning graph (flag: VOYAGER_PLANNER)
                                      ├─ SQLite (per-profile) — trips, conversations, places, journal, usage_log
                                      ├─ Chroma (local) — episodic/semantic memory, journal + places RAG
                                      ├─ MCP travel-tools server (stdio subprocess) — weather, FX
                                      └─ Phoenix tracing (opt-in via env)
```

Chat messages hit `POST /api/conversations/{id}/messages` (SSE stream). Planning-phrase detection (`app/planning/router.py`) routes planning requests to the LangGraph graph; everything else goes through the standard tool-call loop. Graph failure falls back to the single-agent loop.

## Key facts

- **LLM:** OpenRouter via the `openai` SDK (not Anthropic SDK yet — migration planned). Model set by `OPENROUTER_MODEL`, default `anthropic/claude-haiku-4-5`. All calls go through `backend/app/claude.py`; every call is usage-logged (`app/usage.py`).
- **Profiles:** per-user SQLite + Chroma, selected with `backend/scripts/run.sh --profile <name>`.
- **Tests:** backend pytest (real ASGI test client, no mocking Claude/DB at unit level), mcp-server pytest, frontend vitest + Playwright. Run all via the `/test` skill; start servers via `/run`.
- **Migrations:** Alembic; use `bash scripts/migrate.sh` (backs up DB first). `tests/test_migrations.py` exercises new migrations against a seeded DB.

## Sub-documents

- [backend.md](backend.md) — FastAPI layout, routers, tools, conventions, env vars
- [planning.md](planning.md) — LangGraph multi-agent planner: graph, agents, revision scoping
- [memory.md](memory.md) — Chroma memory system, journal/places RAG, extraction pipeline
- [frontend.md](frontend.md) — Next.js 16 / React 19 / Chakra v3 app structure and conventions
- [data-model.md](data-model.md) — SQLite tables, Chroma collections, migrations
- [evals-ops.md](evals-ops.md) — Eval harness, planner feature flag, Phoenix tracing, cost accounting

Also see [OPEN-ITEMS.md](../OPEN-ITEMS.md) (known bugs, deferred decisions, follow-up work — check here before starting anything), [VISION.md](../VISION.md) (roadmap, Month 5–6 scope decisions), [README.md](../README.md) (setup), [docs/multi-agent-planning.md](../docs/multi-agent-planning.md) (planner design doc), and `INCIDENTS.md`.

## Guiding principles

1. Build to learn, not to ship — correctness and understanding over polish.
2. Don't build ahead of the current phase (no auth, Postgres, or deployment work until Month 6).
3. One evolving product — extend Voyager rather than starting parallel apps.
