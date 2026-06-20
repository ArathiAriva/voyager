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
| Month 2 | Trip memory, preference learning, semantic + episodic memory | 🔄 In progress |
| Month 3 | Journal ingestion, RAG over personal travel notes and saved places | — |
| Month 4 | Multi-agent planning (Planner → Research → Critic → Synthesizer) | — |
| Month 5 | Evaluation layer — measure recommendation quality over time | — |
| Month 6 | Production deployment, streaming, auth, caching, observability | — |

### Month 2 progress

- [x] Episodic memory — per-conversation summaries stored in Chroma, retrieved via `search_memory` tool
- [x] Semantic memory — distilled user preferences extracted post-conversation and embedded in Chroma
- [x] Memory retrieval — agent proactively searches memory before answering personalisation-relevant queries
- [ ] Trip journal entries — freeform notes per trip
- [ ] Preference evolution — track how preferences change over time

---

## Architecture

```
┌──────────────────────────┐
│       Next.js UI         │
│     Chat · Trips         │
└──────────┬───────────────┘
           │ HTTP
           ▼
┌──────────────────────────┐        ┌─────────────────────────┐
│     FastAPI Backend      │ stdio  │   MCP Travel Tools      │
│   Agent tool-call loop   │───────▶│   get_weather           │
└───┬──────────────────────┘        │   get_exchange_rate     │
    │                               └─────────────────────────┘
    ├──▶ SQLite
    │    trips · conversations · messages
    │
    └──▶ Chroma (local)
         episodic memory · semantic preferences
```

*Month 4 will introduce LangGraph for multi-agent orchestration and replace the custom loop.*

---

## Tech Stack

| Layer | Tech | Notes |
|-------|------|-------|
| Frontend | Next.js, React, TypeScript, Tailwind, Chakra UI | |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy | |
| Agent loop | Custom tool-call loop (OpenAI-compatible) | LangGraph planned for Month 4 |
| LLM | OpenRouter (Anthropic Claude via API) | Direct Anthropic SDK migration planned |
| Vector DB | Chroma (local) | `all-MiniLM-L6-v2` embeddings, no API key needed; swap to pgvector or Qdrant later |
| Relational DB | SQLite (dev) → PostgreSQL/Supabase (prod) | |
| Embeddings | Chroma built-in (local ONNX) | Swap to OpenAI or Voyage when moving to prod |
| Tool protocol | MCP (stdio) | Weather + exchange rate tools in standalone MCP server |
| Auth | Clerk or Auth.js | Month 6 |
| Evaluation | LangSmith | Month 5 |
| Frontend Deploy | Vercel | Month 6 |
| Backend Deploy | Railway or Fly.io | Month 6 |

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
