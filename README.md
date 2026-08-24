# Voyager — AI Travel Companion

An AI-native travel companion that remembers your trips, helps you plan, and gives real-time travel context. Built as a 6-month learning project covering tool-calling agents, memory systems, RAG, multi-agent orchestration, and MCP.

## Status

Core app is built: chat loop, multi-agent planner, memory, journal + places RAG, evals,
tracing, cost accounting. Current focus is **agent safety evals** (indirect prompt
injection, both planner architectures).

Roadmap, phase definitions, and scope decisions live in [VISION.md](VISION.md).
Known bugs and open work live in [OPEN-ITEMS.md](OPEN-ITEMS.md).

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
       └──▶ Chroma (episodic + semantic memory, journal + saved-places RAG)
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

Run database migrations (backs up the DB first and auto-restores on failure — see INC-001):

```bash
bash scripts/migrate.sh
```

New migrations are also exercised against a seeded database by `tests/test_migrations.py` (runs with the normal pytest suite) — write the migration, run pytest, then migrate.

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

## Evaluation

Two suites, both driving the **real API** so tools, memory, and the planner flag behave as in production. Both take `--planner single|multi|both`.

```sh
cd backend
python -m evals.run                    # quality: 15 golden planning cases, LLM judge
python -m evals.safety_run             # safety: 15 indirect prompt-injection cases
python -m evals.safety_ledger          # aggregate every safety batch, with intervals
```

**Quality** (`evals/run.py`) scores replies on five dimensions and writes a side-by-side planner comparison. The judge defaults to the model under evaluation — pass `--judge-model` to vary it; the report flags the self-preference caveat.

**Safety** (`evals/safety_run.py`) seeds saved places whose text carries an injected instruction, drives a benign turn, and checks whether the agent obeyed. Programmatic checks first, LLM judge only where the failure is qualitative. Design: [docs/safety-evals-spec.md](docs/safety-evals-spec.md).

> Run the safety suite against an **empty** profile (`--profile safetyeval`). Retrieval is semantic, so on a populated profile the fixtures lose to the user's real saved places and most "passes" score a payload the agent never saw. The runner preflights this and refuses to start. The quality suite is the opposite — it wants a *seeded* profile, since several cases test personalisation.

## Observability (Phoenix)

LLM tracing via [Arize Phoenix](https://phoenix.arize.com) (OpenInference + OTel). Disabled by default; enable by setting in `backend/.env`:

```
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces
```

Run Phoenix locally with `phoenix serve` (`pip install arize-phoenix`) or via the portal's compose (service `phoenix`, UI at http://phoenix.localhost or http://localhost:6006). Traces cover both the single-agent loop and the LangGraph planning graph (per-node latency, token usage, prompts/responses) — including eval harness runs, so `python -m evals.run` traces land in the same UI. See `backend/app/observability.py`.

## Cost & token accounting

Every LLM call is recorded to the `usage_log` table (model, prompt/completion tokens, cost, context label). Cost comes from OpenRouter's usage accounting (`usage: {include: true}`), so no local price table. Contexts: `chat`, `planning`, `memory_extraction`, `eval_judge`, `safety_eval`.

- `GET /api/usage/summary?days=30` — totals + breakdowns by model / context / day
- `GET /api/usage/recent?limit=50` — latest calls

Implementation: `app/usage.py` wraps the OpenRouter client once (in `app/claude.py`); recording is fail-open and streaming calls pass through unrecorded. The table is created by `Base.metadata.create_all` at startup (add an Alembic migration if you regenerate a prod DB from migrations only).
