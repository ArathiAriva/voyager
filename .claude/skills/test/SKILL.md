description: Run all tests across backend, MCP server, and frontend

# Test — Voyager

Three separate test suites across three packages. Run them all and report a combined result.

## Backend (pytest, 18 tests)

```bash
cd /Users/aarathi/claude-projects/voyager/backend
source .venv/bin/activate
pytest -v
```

Tests cover:
- Trip CRUD endpoints (`tests/test_trips.py`)
- Conversation CRUD endpoints (`tests/test_conversations.py`)
- `get_trips` tool executor with status filters (`tests/test_tools.py`)

Uses an in-memory SQLite database — no running server needed.

## MCP Server (pytest, 5 tests)

```bash
cd /Users/aarathi/claude-projects/voyager/mcp-server
.venv/bin/pytest -v
```

Tests cover:
- `get_weather` — forecast shaping and unknown destination error (`tests/test_tools.py`)
- `get_exchange_rate` — rate response, lowercase input normalisation, invalid currency error

All external HTTP calls are mocked — no network needed.

## Frontend (vitest, 12 tests)

```bash
cd /Users/aarathi/claude-projects/voyager/frontend
npm test
```

Tests cover all `api.ts` fetch wrappers — success responses and error throwing on non-ok status (`src/tests/api.test.ts`).

## Run all three in sequence

```bash
cd /Users/aarathi/claude-projects/voyager

echo "=== Backend ===" && \
  cd backend && source .venv/bin/activate && pytest -v && cd .. && \
echo "=== MCP Server ===" && \
  cd mcp-server && .venv/bin/pytest -v && cd .. && \
echo "=== Frontend ===" && \
  cd frontend && npm test && cd ..
```

All suites should pass with zero failures before committing.
