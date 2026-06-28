# Voyager Backend

FastAPI backend for the Voyager AI travel companion.

## Stack

- **Python 3.12** with FastAPI and Pydantic v2
- **OpenRouter** (via `openai` SDK) for LLM access — model switchable via env var
- **SQLite** with SQLAlchemy (async) and Alembic migrations
- **Chroma** (local) for semantic memory and journal RAG
- **MCP client** — connects to the Voyager MCP travel tools server for weather and exchange rates

## Project structure

```
backend/
├── app/
│   ├── claude.py          # OpenRouter client singleton
│   ├── db.py              # SQLAlchemy engine and session
│   ├── main.py            # App factory, CORS, router registration, seed data
│   ├── memory.py          # Chroma collections: episodic, semantic, journals
│   ├── mcp_client.py      # MCP stdio client — fetches tool schemas and routes calls
│   ├── tools.py           # Agent tools: get_trips, create_trip, update_trip, search_journal, search_memory
│   ├── models/            # Pydantic + ORM models
│   └── routers/
│       ├── conversations.py  # Persistent conversations + agentic loop
│       ├── trips.py          # Trip CRUD
│       ├── journal.py        # Journal entries (embeds into Chroma on save)
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
cp profiles/.env.egwene .env
# restart uvicorn
```

Each profile stores its data in:
- `data/{profile}.db` — SQLite (trips, journals, conversations)
- `chroma_{profile}/` — Chroma (episodic memory, semantic preferences, journal embeddings)

### Seeding a profile

With the backend running on the target profile:

```bash
python scripts/seed.py --profile egwene
```

This creates trips and journal entries via the API, which automatically triggers Chroma embedding and memory extraction for each entry. Run once per fresh profile DB.

## Running

```bash
cp profiles/.env.egwene .env   # or whichever profile
uvicorn app.main:app --reload
```

API at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

The MCP server is launched automatically as a subprocess when the agent loop first receives a message — no separate startup required.

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | Yes | — | OpenRouter API key |
| `OPENROUTER_MODEL` | No | `anthropic/claude-haiku-4-5` | Any OpenRouter model string |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./voyager.db` | SQLite path |
| `CHROMA_PATH` | No | `./chroma_db` | Chroma persistence directory |

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
| GET | `/api/conversations` | List conversations |
| POST | `/api/conversations` | Create conversation |
| GET | `/api/conversations/{id}` | Get conversation with messages |
| POST | `/api/conversations/{id}/messages` | Send message (agentic loop) |
| DELETE | `/api/conversations/{id}` | Delete conversation |
| GET | `/api/memories` | Read episodic + semantic memory |

## Troubleshooting

**Port 8000 already in use**

```bash
kill $(lsof -ti :8000)
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
