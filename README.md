# Voyager — AI Travel Companion

An AI-native travel companion that remembers your trips, helps you plan, and gives real-time travel context. Built as a 6-month learning project covering tool-calling agents, memory systems, RAG, multi-agent orchestration, and MCP.

## Status

| Month | Theme | Status |
|-------|-------|--------|
| 1 | Core agent loop, tool calling, MCP | ✅ Done |
| 2 | Memory system (episodic + semantic), journal RAG | ✅ Done |
| 3 | Multi-profile support, saved places, LLM-generated seed data | ✅ Done |
| 4 | Multi-agent trip planning (LangGraph) | ✅ Done |
| 5 | — | Upcoming |
| 6 | — | Upcoming |

### Month 4 highlights

- **LangGraph multi-agent planner** — `plan my 7 days in Kyoto` triggers a graph with parallel researcher agents (activities, food, logistics), followed by accommodation selection, geospatial optimization, and a critic review loop
- **Intent classification** — vague requests (`let's plan a trip to Hawaii`) get a clarifying question before any research runs
- **Revision support** — `find cheaper restaurants` re-runs only the food researcher, not the full graph
- **Auto-saved places** — all LLM-recommended places (attractions, restaurants, hotels) are saved to Saved Places with a Google Maps link after planning completes

---

## Architecture

```
┌─────────────────┐
│   Next.js UI    │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────────────────────────────────────────┐
│  FastAPI Backend                                     │
│                                                      │
│  ┌──────────────┐    ┌──────────────────────────┐   │
│  │ Agent Loop   │    │ Planning Graph (LangGraph)│   │
│  │ (general     │    │                           │   │
│  │  chat, tools)│    │  classify → researchers   │   │
│  └──────────────┘    │  → optimizer → critic     │   │
│                      │  → assemble + persist     │   │
│                      └──────────────────────────┘   │
└──────┬──────────────────────────┬───────────────────┘
       │                          │ stdio
       │                          ▼
       │                 ┌──────────────────────────┐
       │                 │  MCP Travel Tools Server  │
       │                 │  get_weather              │
       │                 │  get_exchange_rate         │
       │                 └──────────────────────────┘
       │
       ├──▶ SQLite (trips, conversations, messages, saved places)
       │
       └──▶ Chroma (episodic + semantic memory, journal RAG)
```

Planning messages are intercepted before the standard agent loop and routed to the LangGraph graph. Non-planning messages go through the standard tool-call loop. Both paths share the same DB session and memory system.

---

## Prerequisites

- Python 3.12+
- Node.js 18+
- An [OpenRouter](https://openrouter.ai) API key

---

## Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy the env file and add your key:

```bash
cp .env.example .env
# Set OPENROUTER_API_KEY in .env
```

Run database migrations:

```bash
alembic upgrade head
```

Start the dev server:

```bash
uvicorn app.main:app --reload
```

Or use the profile script (recommended — handles per-profile DB and env):

```bash
bash scripts/run.sh --profile rand
```

API available at `http://localhost:8060`. Interactive docs at `http://localhost:8060/docs`.

### Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | Yes | — | OpenRouter API key |
| `OPENROUTER_MODEL` | No | `anthropic/claude-haiku-4-5` | Any OpenRouter model string |

---

## MCP Travel Tools Server

Standalone MCP server exposing external travel APIs. Runs as a subprocess of the backend — no separate startup needed in development.

```bash
cd mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

To run it directly (e.g. to connect from Claude Code):

```bash
python server.py
```

### Tools

| Tool | API | Description |
|------|-----|-------------|
| `get_weather` | Open-Meteo | 7-day forecast for any destination |
| `get_exchange_rate` | Frankfurter | Live exchange rate between two currencies |

No API keys required — both APIs are free and open.

### Connecting to Claude Code

Add to your Claude Code MCP config (`~/.claude/mcp_config.json` or project `.claude/mcp_config.json`):

```json
{
  "mcpServers": {
    "voyager-travel-tools": {
      "command": "/path/to/voyager/mcp-server/.venv/bin/python",
      "args": ["/path/to/voyager/mcp-server/server.py"]
    }
  }
}
```

---

## Memory system

Voyager has an episodic and semantic memory system backed by [Chroma](https://www.trychroma.com/) running locally.

| Memory type | What's stored | How it's used |
|-------------|--------------|----------------|
| Episodic | One-sentence summary of each conversation | Retrieved when past experiences are relevant |
| Semantic | Distilled user preferences (e.g. "prefers boutique hotels") | Retrieved to personalise recommendations |
| Journal RAG | Full journal entries embedded per trip | Retrieved by `search_journal` tool for context |

After each reply the backend runs a background LLM pass to extract the episode and any preferences, then upserts them into Chroma. The agent has a `search_memory` tool it calls proactively when personalisation would help.

**Embeddings:** Chroma's built-in `all-MiniLM-L6-v2` model (runs locally via ONNX, no API key needed). The model (~80 MB) is downloaded on first use to `~/.cache/chroma/`. Chroma data persists to `backend/chroma_db/`.

---

## Frontend

```bash
cd frontend
npm install
```

Start the dev server:

```bash
npm run dev
```

UI available at `http://localhost:3000`.

---

## Running everything

Open two terminals:

```bash
# Terminal 1 — backend (replace rand with any profile)
cd backend && bash scripts/run.sh --profile rand

# Terminal 2 — frontend
cd frontend && npm run dev
```

The MCP server does **not** need a separate terminal. The backend uses stdio transport, which spawns `server.py` as a subprocess on demand whenever the agent calls a travel tool (`get_weather`, `get_exchange_rate`). The only requirement is that the MCP server's `.venv` is set up (see MCP setup above).
