description: Launch the Voyager backend (FastAPI :8060) and frontend (Next.js :3000)

# Run — Voyager

Two servers need to be running: the FastAPI backend and the Next.js frontend. The MCP server does **not** need a separate process — it is spawned automatically by the backend agent loop via stdio.

## Prerequisites

Ensure both venvs and node_modules are installed:

```bash
# Backend
cd /Users/aarathi/claude-projects/voyager/backend
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
alembic upgrade head

# MCP server venv (needed by the backend subprocess)
cd /Users/aarathi/claude-projects/voyager/mcp-server
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt

# Frontend
cd /Users/aarathi/claude-projects/voyager/frontend
[ -d node_modules ] || npm install
```

## Run

Start both servers in the background from the repo root:

```bash
cd /Users/aarathi/claude-projects/voyager

# Backend
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8060 > /tmp/voyager-backend.log 2>&1 &
BACKEND_PID=$!
cd ..

# Frontend
cd frontend && npm run dev > /tmp/voyager-frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..
```

## Verify

Wait for both to be ready, then confirm:

```bash
# Backend health check
for i in {1..20}; do
  curl -sf http://localhost:8060/health > /dev/null && break
  sleep 0.5
done
curl -s http://localhost:8060/health
# → {"status":"ok"}

# Frontend (307 redirect to /chat is expected)
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
# → 307 or 200
```

Logs:
- Backend: `/tmp/voyager-backend.log`
- Frontend: `/tmp/voyager-frontend.log`

## Stop

```bash
kill $(lsof -ti :8060) 2>/dev/null && echo "backend stopped"
kill $(lsof -ti :3000) 2>/dev/null && echo "frontend stopped"
```

## Environment

The backend requires a `.env` file at `backend/.env`:

| Variable | Required | Default | Notes |
|---|---|---|---|
| `OPENROUTER_API_KEY` | Yes | — | OpenRouter API key |
| `OPENROUTER_MODEL` | No | `anthropic/claude-haiku-4-5` | Any OpenRouter model string |
