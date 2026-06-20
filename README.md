# Voyager — AI Travel Companion

An AI-native travel companion that remembers your trips, helps you plan, and gives real-time travel context. Built as a 6-month learning project covering tool-calling agents, memory systems, RAG, multi-agent orchestration, and MCP.

## Architecture

```
┌─────────────────┐
│   Next.js UI    │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐        ┌──────────────────────────┐
│  FastAPI        │ stdio  │  MCP Travel Tools Server  │
│  Backend +      │───────▶│  get_weather              │
│  Agent Loop     │        │  get_exchange_rate         │
└────────┬────────┘        └──────────────────────────┘
         │
         ├──▶ SQLite (trips, conversations, messages)
         │
         └──▶ Chroma (episodic + semantic memory)
```

The backend runs the agentic tool-call loop. Tools that need the local database (`get_trips`) live in the backend. External API tools (`get_weather`, `get_exchange_rate`) live in the MCP server — independently reusable by any MCP-compatible agent.

The memory system runs entirely locally — no external API needed. After each conversation, the agent extracts a summary (episodic) and any revealed preferences (semantic) and stores them in Chroma using the `all-MiniLM-L6-v2` embedding model. On subsequent conversations the agent can call `search_memory` to retrieve relevant context.

## Project structure

```
voyager/
├── backend/          # FastAPI backend + agent loop + memory system
├── frontend/         # Next.js chat UI
└── mcp-server/       # Voyager MCP travel tools server
```

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

API available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key |
| `OPENROUTER_MODEL` | No | Model override (default: `anthropic/claude-haiku-4-5`) |

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
# Terminal 1 — backend
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload

# Terminal 2 — frontend
cd frontend && npm run dev
```

The MCP server does **not** need a separate terminal. The backend uses stdio transport, which spawns `server.py` as a subprocess on demand whenever the agent calls a travel tool (`get_weather`, `get_exchange_rate`). The only requirement is that the MCP server's `.venv` is set up (see MCP setup above).
