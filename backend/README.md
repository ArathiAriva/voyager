# Voyager Backend

FastAPI backend for the Voyager AI travel companion.

## Stack

- **Python 3.12** with FastAPI and Pydantic v2
- **Anthropic SDK** (`anthropic`) for Claude model access
- **uvicorn** as the ASGI server

## Project structure

```
backend/
├── app/
│   ├── claude.py        # Anthropic client singleton
│   ├── main.py          # App factory, CORS, router registration
│   ├── models/          # Pydantic request/response models
│   │   ├── chat.py
│   │   └── trip.py
│   └── routers/         # Route handlers
│       ├── chat.py      # POST /api/chat
│       └── trips.py     # GET /api/trips
├── .env.example
└── requirements.txt
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
```

## Running

```bash
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`. Interactive docs at `/docs`.

## Troubleshooting

**Port 8000 already in use**

A previous uvicorn process is still running. Find and kill it:

```bash
kill $(lsof -ti :8000)
```

Then restart normally. Alternatively, run on a different port:

```bash
uvicorn app.main:app --reload --port 8001
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/chat` | Send a chat message |
| GET | `/api/trips` | List trips |

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for Claude |
