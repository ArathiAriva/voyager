# Voyager Backend

FastAPI backend for the Voyager AI travel companion.

## Stack

- **Python 3.12** with FastAPI and Pydantic v2
- **OpenRouter** (via `openai` SDK) for LLM access — model switchable via env var
- **SQLite** with SQLAlchemy (async) and Alembic migrations
- **Chroma** (local) for semantic memory and journal RAG
- **LangGraph** for multi-agent trip planning orchestration
- **MCP client** — connects to the Voyager MCP travel tools server for weather and exchange rates

## Project structure

```
backend/
├── app/
│   ├── claude.py          # OpenRouter client + llm_call() helper with per-call model override
│   ├── db.py              # SQLAlchemy engine and session
│   ├── main.py            # App factory, CORS, router registration, seed data
│   ├── memory.py          # Chroma collections: episodic, semantic, journals, saved places
│   ├── mcp_client.py      # MCP stdio client — fetches tool schemas and routes calls
│   ├── tools.py           # Agent tools: save_place, search_places, get_trips, set_itinerary, ...
│   ├── models/            # Pydantic + ORM models
│   ├── agents/            # Per-agent modules for the planning graph
│   │   ├── __init__.py    # parse_json_response() — robust JSON extraction from LLM output
│   │   ├── planner.py     # Orchestrator: classify intent, build brief, assemble reply
│   │   ├── activities.py  # Attractions and experiences researcher
│   │   ├── food.py        # Restaurants and cafes researcher
│   │   ├── accommodation.py # Hotel researcher (runs after activities + food)
│   │   ├── logistics.py   # Transport and timing researcher
│   │   ├── optimizer.py   # Clusters researcher outputs into a day-by-day itinerary
│   │   └── critic.py      # Scores itinerary draft; triggers revision loop if score < 4
│   ├── planning/
│   │   ├── state.py       # PlanningState TypedDict + RevisionScope
│   │   ├── graph.py       # LangGraph StateGraph: nodes, edges, revision loop, place auto-save
│   │   └── router.py      # is_planning_request() + run_planning_graph()
│   └── routers/
│       ├── conversations.py  # Persistent conversations + agentic loop (planning branch + standard loop)
│       ├── trips.py          # Trip CRUD
│       ├── places.py         # Saved places CRUD + background enrichment
│       ├── journal.py        # Journal entries (auto-embeds in Chroma on save)
│       ├── content.py        # Connected content (photos, links)
│       └── memories.py       # Read episodic + semantic memory
├── alembic/               # DB migrations
├── data/                  # SQLite DB files, one per profile (gitignored)
├── chroma_*/              # Chroma vector stores, one per profile (gitignored)
├── profiles/              # Per-profile .env files (gitignored)
│   ├── .env.egwene
│   ├── .env.rand
│   ├── .env.nynaeve
│   ├── .env.mat
│   ├── .env.perrin
│   ├── .env.lan
│   └── .env.moiraine
├── scripts/
│   ├── run.sh             # Start backend with a named profile (sets DB_PATH, CHROMA_PATH, loads .env)
│   └── seed.py            # Seeds trips + journal entries for a profile via the API
└── requirements.txt
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Profiles

Each profile is an isolated SQLite DB + Chroma instance representing a different test user. Profiles are named after characters from the Wheel of Time series.

| Profile | Travel style |
|---------|-------------|
| `egwene` | Cultural explorer — museums, history, plans ahead (primary dev profile) |
| `rand` | Impulsive wilderness solo — no plan, things work out |
| `nynaeve` | Wellness + slow travel — yoga retreats, forest walks |
| `mat` | Nightlife + festivals — zero plan, maximum luck |
| `perrin` | Forests + small towns — hiking, minimal cities |
| `lan` | Remote/austere — long treks, fog, silence |
| `moiraine` | Ancient ruins + archives — deliberate, historically obsessed |

### Switching profiles

```bash
bash scripts/run.sh --profile egwene
```

Each profile stores its data in:
- `data/{profile}.db` — SQLite (trips, journals, conversations, saved places)
- `chroma_{profile}/` — Chroma (episodic memory, semantic preferences, journal embeddings)

### Seeding a profile

With the backend running on the target profile:

```bash
python scripts/seed.py --profile egwene
```

This creates trips and journal entries via the API, which automatically triggers Chroma embedding and memory extraction for each entry. Run once per fresh profile DB.

## Running

```bash
bash scripts/run.sh --profile rand
```

API at `http://localhost:8060`. Docs at `http://localhost:8060/docs`.

The MCP server is launched automatically as a subprocess when the agent loop first receives a message — no separate startup required.

## Planning graph

When the backend receives a message that matches a planning phrase (`plan my`, `itinerary`, `days in`, etc.) it routes to the LangGraph multi-agent graph instead of the standard loop.

```
load_context → classify_intent
  ├─ needs_info → clarify → END   (asks for destination/duration if missing)
  └─ full_plan / revision
       ├─ activities_researcher ─┐
       ├─ food_researcher        ├─▶ accommodation_researcher → optimizer → critic
       └─ logistics_researcher ──┘        │                                   │
                                          │ score ≥ 4                score < 4 (max 2x)
                                          ▼                                   ▼
                                   assemble_reply ◀─────────── targeted_revision
                                          │
                                   persist_itinerary → END
                                   (saves itinerary + auto-saves all recommended places)
```

Revision messages (`find cheaper restaurants`, `redo the accommodation`) re-run only the affected researchers via `RevisionScope`, not the full graph.

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | Yes | — | OpenRouter API key |
| `OPENROUTER_MODEL` | No | `anthropic/claude-haiku-4-5` | Any OpenRouter model string |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./voyager.db` | SQLite path (set by run.sh) |
| `CHROMA_PATH` | No | `./chroma_db` | Chroma persistence directory (set by run.sh) |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/trips` | List trips |
| POST | `/api/trips` | Create trip |
| PATCH | `/api/trips/{id}` | Update trip |
| DELETE | `/api/trips/{id}` | Delete trip |
| GET | `/api/trips/{id}/journal` | List journal entries |
| POST | `/api/trips/{id}/journal` | Add journal entry (auto-embeds in Chroma) |
| PATCH | `/api/trips/{id}/journal/{eid}` | Update journal entry |
| DELETE | `/api/trips/{id}/journal/{eid}` | Delete journal entry |
| GET | `/api/trips/{id}/content` | List connected content |
| POST | `/api/trips/{id}/content` | Add connected content |
| DELETE | `/api/trips/{id}/content/{cid}` | Remove connected content |
| GET | `/api/trips/{id}/places` | List saved places |
| POST | `/api/trips/{id}/places` | Save a place (triggers background enrichment if URL provided) |
| PATCH | `/api/trips/{id}/places/{pid}` | Update saved place |
| DELETE | `/api/trips/{id}/places/{pid}` | Delete saved place |
| GET | `/api/conversations` | List conversations |
| POST | `/api/conversations` | Create conversation |
| GET | `/api/conversations/{id}` | Get conversation with messages |
| POST | `/api/conversations/{id}/messages` | Send message (planning graph or standard agent loop) |
| DELETE | `/api/conversations/{id}` | Delete conversation |
| GET | `/api/memories` | Read episodic + semantic memory |

## Troubleshooting

**Port 8000 already in use**

```bash
kill $(lsof -ti :8060)
```

**New profile DB has no tables**

Alembic can silently no-op on a fresh SQLite file. The seed script handles this automatically via `create_all`. If you need to initialize manually:

```bash
python -c "
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine
from app.db import Base
import app.models.orm

async def main():
    engine = create_async_engine(os.environ['DATABASE_URL'])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

asyncio.run(main())
"
```

**Planning graph returns a fallback message**

Check backend logs for `voyager.planning` logger output. Common causes:
- `critic_score` stuck at 2–3: the critic prompt has a "4 is the default pass" instruction; if it still fails, the graph exhausts 2 revision attempts and proceeds anyway
- JSON parse failures from researchers: `parse_json_response` handles prose + fenced JSON; check for truly malformed output
- `trip_id` not resolved: the planner calls `get_trips` to match the destination; if no trip exists for the destination, `persist_itinerary` is skipped but the reply still works
