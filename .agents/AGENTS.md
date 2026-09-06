# Voyager — Agent Context

Voyager is an AI travel companion (chat, trip planning, memory, journal RAG) built as a 6-month AI-engineering learning project. Currently at Month 4.5–4.75 of 6: single-agent chat loop + LangGraph multi-agent planner are both live, feature-flagged for A/B evals.

**Deploying for real use (2026-09-06).** A real Halifax trip on **Sept 18–21** is
the current driver, which pulls some Month 6 work forward. `app/auth.py` adds a
**shared-token lock** — explicitly *not* a step toward multi-user, since isolation
here is process-level and would fail silently if one process served two users. Still
to do: mobile layout fixes (the sidebar defaults to 288px of a 390px screen), a
Dockerfile with the 166 MB Chroma model baked in, and a **persistent volume** —
SQLite and Chroma are files, so a redeploy without one wipes everything.

**Nothing in `backend/data/` or `backend/chroma_*/` is in git.** That data exists
only on the dev machine.

**Active workstream (2026-09-03): core product flow.** Voyager is first an AI-engineering / LLM-app project — making the chat → trip → itinerary path feel natural comes before safety work. The **indirect prompt-injection safety eval suite** (`backend/evals/safety_*`) is **paused**, not abandoned: the suite, its `results/`, and `SAFETY-LEDGER.md` stay in place and resume later. Don't start safety-eval work (S-1b, S-3, S-4, S-5, S-9, S-10) unless the user asks. See [OPEN-ITEMS.md](../OPEN-ITEMS.md) for what's parked and what isn't.

## System at a glance

```
Next.js 16 UI (:3000) ──HTTP/SSE──▶ FastAPI backend (:8060)
                                      ├─ Single-agent chat loop (tool calling)
                                      ├─ LangGraph planning graph (flag: VOYAGER_PLANNER)
                                      ├─ SQLite (per-profile) — trips, conversations, places, journal, usage_log
                                      ├─ Chroma (local) — episodic/semantic memory, journal + places RAG
                                      ├─ MCP travel-tools server (stdio subprocess) — weather, FX
                                      └─ Phoenix tracing (opt-in) + local JSONL LLM trace
```

Chat messages hit `POST /api/conversations/{id}/messages` (SSE stream). Planning-phrase detection (`app/planning/router.py`) routes planning requests to the LangGraph graph; everything else goes through the standard tool-call loop. Graph failure falls back to the single-agent loop.

## Key facts

- **LLM:** OpenRouter via the `openai` SDK (not Anthropic SDK yet — migration planned). Model set by `OPENROUTER_MODEL`, default `anthropic/claude-haiku-4-5`. All calls go through `backend/app/claude.py`; every call is usage-logged (`app/usage.py`).
- **Profiles:** per-user SQLite + Chroma, selected with `backend/scripts/run.sh --profile <name>`.
- **Tests:** backend pytest (real ASGI test client, no mocking Claude/DB at unit level), mcp-server pytest, frontend vitest + Playwright. Run all via the `/test` skill; start servers via `/run`. **253 backend / 35 frontend passing as of 2026-09-06**; the `test_content.py` failures noted here previously were fixed in B-3.
- **Evals:** quality (`evals/run.py`, 15 golden cases) and safety (`evals/safety_run.py`, 15 injection cases). Both take `--planner single|multi|both`. The safety suite needs an **empty** profile (`--profile safetyeval`); the quality suite wants a *seeded* one. Don't mix them up — on a populated profile safety fixtures lose retrieval to real data and produce vacuous passes.
- **Migrations:** Alembic; use `bash scripts/migrate.sh` (backs up DB first). `tests/test_migrations.py` exercises new migrations against a seeded DB.

## Sub-documents

- [backend.md](backend.md) — FastAPI layout, routers, tools, conventions, env vars
- [planning.md](planning.md) — LangGraph multi-agent planner: graph, agents, revision scoping
- [memory.md](memory.md) — Chroma memory system, journal/places RAG, extraction pipeline
- [frontend.md](frontend.md) — Next.js 16 / React 19 / Chakra v3 app structure and conventions
- [data-model.md](data-model.md) — SQLite tables, Chroma collections, migrations
- [evals-ops.md](evals-ops.md) — Eval harness, planner feature flag, Phoenix tracing, cost accounting

Before committing work that changes architecture, data flow, a schema, or an operational procedure, run the `/sync-docs` skill — it checks which of these docs the change made stale.

Also see [OPEN-ITEMS.md](../OPEN-ITEMS.md) (known bugs, deferred decisions, follow-up work — check here before starting anything), [VISION.md](../VISION.md) (roadmap, Month 5–6 scope decisions), [README.md](../README.md) (setup), [docs/multi-agent-planning.md](../docs/multi-agent-planning.md) (planner design doc), and `INCIDENTS.md`.

## Guiding principles

1. Build to learn, not to ship — correctness and understanding over polish.
2. Don't build ahead of the current phase (no auth, Postgres, or deployment work until Month 6).
3. One evolving product — extend Voyager rather than starting parallel apps.
