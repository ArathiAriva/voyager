# Voyager Backend

FastAPI backend for the Voyager AI travel companion.

## Stack

- **Python 3.12** with FastAPI and Pydantic v2
- **OpenRouter** (via `openai` SDK) for LLM access — model switchable via env var
- **SQLite** with SQLAlchemy (async) and Alembic migrations
- **MCP client** — connects to the Voyager MCP travel tools server for weather and exchange rates

## Project structure

```
backend/
├── app/
│   ├── claude.py          # OpenRouter client singleton
│   ├── db.py              # SQLAlchemy engine and session
│   ├── main.py            # App factory, CORS, router registration
│   ├── mcp_client.py      # MCP stdio client — fetches tool schemas and routes calls
│   ├── tools.py           # Local tool executors (get_trips)
│   ├── models/            # Pydantic + ORM models
│   └── routers/
│       ├── chat.py        # POST /api/chat (stateless)
│       ├── conversations.py  # Persistent conversations + agentic loop
│       └── trips.py       # Trip CRUD
├── alembic/               # DB migrations
├── .env.example
└── requirements.txt
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set OPENROUTER_API_KEY in .env
```

Run migrations:

```bash
alembic upgrade head
```

## Running

```bash
uvicorn app.main:app --reload
```

API at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

The MCP server is launched automatically as a subprocess when the agent loop first receives a message — no separate startup required.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key |
| `OPENROUTER_MODEL` | No | Model override (default: `anthropic/claude-haiku-4-5`) |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/chat` | Stateless chat |
| GET | `/api/trips` | List trips |
| POST | `/api/trips` | Create trip |
| GET | `/api/conversations` | List conversations |
| POST | `/api/conversations` | Create conversation |
| POST | `/api/conversations/{id}/messages` | Send message (agentic loop) |
| DELETE | `/api/conversations/{id}` | Delete conversation |

## Troubleshooting

**Port 8000 already in use**

```bash
kill $(lsof -ti :8000)
```
