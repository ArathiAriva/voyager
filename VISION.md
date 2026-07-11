# Voyager — AI Travel Companion

## Vision

Voyager is an AI-native solo travel companion that understands not just where you want to go, but *how* you travel and what travel means to you. It remembers your past trips, learns your preferences, helps you plan with intelligence, and reflects your journey back to you over time.

> "An AI that augments human meaning-making through travel."

---

## What Voyager Does

- **Plan** — Generate itineraries tailored to your travel style, not generic tourist routes
- **Remember** — Build a personal memory of your trips, preferences, and reflections
- **Research** — Dispatch agents to gather real-time info on places, weather, and logistics
- **Reflect** — Surface patterns in how you travel and what you value
- **Recommend** — Suggest destinations, experiences, and media based on your history

---

## Core Features (by phase)

| Phase | Feature | Status |
|-------|---------|--------|
| Month 1 | Chat interface, itinerary generation, basic tool use (weather, exchange rates via MCP) | ✅ Done |
| Month 2 | Trip memory, preference learning, semantic + episodic memory | ✅ Done |
| Month 3 | Journal ingestion, RAG over personal travel notes and saved places | ✅ Done |
| Month 4 | Multi-agent planning (Planner → Research → Critic → Synthesizer) | ✅ Done |
| Month 4.5 | Eval harness, planner feature flag, observability (Phoenix), cost/token accounting | ✅ Done |
| Month 5 | Run single-vs-multi evals; retrieval quality metrics; preference evolution; LangSmith datasets | — |
| Month 6 | Production deployment (web only), auth, PostgreSQL/pgvector, rate limits & quotas, caching | — |

### Month 2 — complete

- [x] Episodic memory — per-conversation summaries stored in Chroma, retrieved via `search_memory` tool
- [x] Semantic memory — distilled user preferences extracted post-conversation and embedded in Chroma
- [x] Memory retrieval — agent proactively searches memory before answering personalisation-relevant queries
- [x] Trip journal entries — freeform notes per trip, date-stamped, multi-source (app / telegram / email)
- [x] Connected content — attach photos, Instagram, TikTok, blog links to a trip
- [x] Memory views — dedicated UI page surfacing episodic and semantic memories
- [x] Active trip status — trips can be marked active; distinct badge + card styling
- [x] Itinerary generation + storage — agent can plan and persist a day-by-day itinerary per trip; Itinerary tab in UI
- [x] Multi-profile support — per-user SQLite + Chroma, switchable via `--profile` flag
- [x] LLM-generated seed data — realistic profiles for development and testing
- [ ] Preference evolution — deferred to Month 5; needs real usage data to be meaningful, pairs naturally with the evaluation layer

### Month 3 — complete

- [x] Journal RAG — semantic search over journal entries via `search_journal` tool; Chroma embeddings auto-indexed on write
- [x] Saved places — save places (restaurants, hotels, neighbourhoods) from chat or manually; Jina Reader enrichment for summaries, OG thumbnail fetch, Chroma embeddings for RAG; agent tools `save_place` + `search_places`; Places tab with card grid and detail modal

### Month 4 — complete

- [x] Multi-agent planning — LangGraph graph (`backend/app/planning/`) with specialist agents: planner, activities, food, accommodation, logistics, optimizer, critic; revision support scopes re-runs to affected domains
- [x] Intent routing — planning-phrase detection routes chat messages to the graph; non-planning messages stay on the single-agent loop
- [x] Streamed progress — graph nodes emit step labels surfaced live in the chat UI
- [x] Graceful fallback — graph failure falls back to the single-agent loop

### Month 4.5 — complete (evaluation & ops foundations, pulled forward from Months 5–6)

- [x] Planner feature flag — `VOYAGER_PLANNER` env + per-request override (`app/flags.py`) to A/B single-agent vs multi-agent in the same process
- [x] Eval harness — 15-case golden set, LLM-as-judge (5 dimensions, temperature 0), runner comparing both planners through the real API with JSON results + markdown report (`backend/evals/`); output shape is LangSmith-feedback-compatible
- [x] Observability — Phoenix (OpenInference/OTel) tracing of both LLM paths; per-node latency, tokens, prompts (`app/observability.py`, opt-in via env)
- [x] Cost/token accounting — every LLM call logged with OpenRouter-reported cost and context label (chat / planning / memory / eval_judge); `/api/usage` endpoints + Usage tab in the UI

---

## Architecture

```
┌──────────────────────────────────────┐
│              Next.js UI                    │
│ Chat · Trips · Journal · Memories · Usage  │
└──────────────┬───────────────────────┘
               │ HTTP
               ▼
┌──────────────────────────────────┐        ┌─────────────────────────┐
│         FastAPI Backend          │ stdio  │   MCP Travel Tools      │
│  Single-agent loop (chat)        │───────▶│   get_weather           │
│  LangGraph planning graph        │        │   get_exchange_rate     │
│  (feature-flagged via            │        └─────────────────────────┘
│   VOYAGER_PLANNER / request)     │
└───┬──────────────────────────────┘
    ├──▶ SQLite
    │    trips · itineraries · journal entries · usage_log
    │    connected content · conversations · messages
    │
    ├──▶ Chroma (local)
    │    episodic memory · semantic preferences · journal RAG
    │
    └──▶ Phoenix (optional, OTel)
         traces for both agent paths + eval runs
```

*Evals live in `backend/evals/` and exercise both planners through the real API.*

---

## Tech Stack

| Layer | Tech | Notes |
|-------|------|-------|
| Frontend | Next.js, React, TypeScript, Tailwind, Chakra UI | |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy | |
| Agent loop | Single-agent loop + LangGraph planning graph | Feature-flagged; both paths kept for A/B evals |
| LLM | OpenRouter (Anthropic Claude via API) | Direct Anthropic SDK migration planned; usage accounting via OpenRouter cost reporting |
| Vector DB | Chroma (local) | `all-MiniLM-L6-v2` embeddings, no API key needed; swap to pgvector or Qdrant later |
| Relational DB | SQLite (dev) → PostgreSQL/Supabase (prod) | |
| Embeddings | Chroma built-in (local ONNX) | Swap to OpenAI or Voyage when moving to prod |
| Tool protocol | MCP (stdio) | Weather + exchange rate tools in standalone MCP server |
| Auth | Clerk or Auth.js | Month 6 |
| Evaluation | Custom harness (`backend/evals/`), LangSmith-ready | LangSmith datasets in Month 5 |
| Observability | Arize Phoenix (local, OpenInference/OTel) | In place; LangSmith can coexist later |
| Cost accounting | `usage_log` + `/api/usage` + Usage tab | In place |
| Frontend Deploy | Vercel | Month 6 |
| Backend Deploy | Railway or Fly.io (container — planning runs are too long for serverless) | Month 6 |

### Month 6 scope notes (decided 2026-07-05)

- **Web app only.** No Android/iOS in this project — a PWA manifest is the most we'd add. A native mobile app is a separate learning effort (mobile engineering, not AI engineering) and must not crowd out Months 5–6.
- Deployment shape: Vercel (frontend) + Railway/Fly container (backend) + Supabase (Postgres + auth + pgvector, collapsing SQLite and Chroma into one store).
- Production additions beyond deploy: multi-tenant auth (`user_id` through every table/collection), per-user rate limits and LLM budget quotas (built on the usage accounting), secrets management, CI running pytest + eval harness as regression gates.

---

## Learning Goals

This project is the primary vehicle for reaching **AI Engineering Level 4** (multi-agent system designer) within 6 months, covering:

- Tool-calling agents (deep)
- Memory systems — semantic, episodic, reflection (medium)
- RAG & retrieval (medium)
- Multi-agent orchestration with LangGraph (medium)
- MCP server design (medium)
- Evaluation with LLM judges (medium)
- Production deployment (light)

**Intentionally skipped:** fine-tuning, training pipelines, GPU infrastructure.

---

## Guiding Principles

1. **Build to learn, not to ship** — correctness and understanding over polish
2. **Breadth over depth** — cover the AI engineering map, don't rabbit-hole
3. **One evolving product** — add capabilities to Voyager rather than starting fresh
4. **Understand the infrastructure** — know enough about each layer to reason about tradeoffs (like ECS/Lambda)
