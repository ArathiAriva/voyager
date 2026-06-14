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

| Phase | Feature |
|-------|---------|
| Month 1 | Chat interface, itinerary generation, basic tool use (search, weather) |
| Month 2 | Trip memory, preference learning, semantic + episodic memory |
| Month 3 | Journal ingestion, RAG over personal travel notes and saved places |
| Month 4 | Multi-agent planning (Planner → Research → Critic → Synthesizer) |
| Month 5 | Evaluation layer — measure recommendation quality over time |
| Month 6 | Production deployment, streaming, auth, caching, observability |

---

## Architecture

```
┌──────────────────────────┐
│       Next.js UI         │
│  Chat · Maps · Journals  │
└──────────┬───────────────┘
           │ HTTPS
           ▼
┌──────────────────────────┐
│     FastAPI Backend      │
│  Auth · Sessions · API   │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│    Agent Orchestrator    │
│        LangGraph         │
└───┬────────┬────────┬────┘
    │        │        │
    ▼        ▼        ▼
Memory   Retrieval   Tools
System    (RAG)      Layer
    │        │        │
    ▼        ▼        ▼
 Qdrant  LlamaIndex  MCP
 Postgres            Server
```

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js, React, TypeScript, Tailwind, Chakra UI |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy |
| AI Orchestration | LangGraph |
| LLM | Anthropic Claude / OpenAI |
| Vector DB | Qdrant |
| Relational DB | PostgreSQL (Supabase) |
| Embeddings | OpenAI or Voyage |
| Auth | Clerk or Auth.js |
| Evaluation | LangSmith |
| Frontend Deploy | Vercel |
| Backend Deploy | Railway or Fly.io |

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
