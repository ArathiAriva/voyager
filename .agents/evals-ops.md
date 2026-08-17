# Evals, feature flag, observability, cost

## Planner feature flag (`backend/app/flags.py`)

`VOYAGER_PLANNER` env (`single` | `multi`) with per-request override, so single-agent and multi-agent planners can be A/B'd in the same process. This is the backbone of the eval comparisons — keep both paths working.

## Eval harness (`backend/evals/`)

- `golden_set.json` — 15 planning cases.
- `judge.py` — LLM-as-judge, 5 dimensions, temperature 0 (usage context `eval_judge`).
- `run.py` — runs both planners through the **real API** (`python -m evals.run`), writes timestamped results to `evals/results/<ts>/` (`single.json`, `multi.json`, `report.md`). Output shape is LangSmith-feedback-compatible (LangSmith datasets planned for Month 5).

Eval runs are traced by Phoenix like normal traffic.

## Observability (`backend/app/observability.py`)

Arize Phoenix via OpenInference/OTel. Opt-in: set `PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces` in `backend/.env`; `setup_tracing()` is a no-op otherwise. Covers both the single-agent loop and every LangGraph node (latency, tokens, prompts/responses). Run Phoenix with `phoenix serve` (local, free — no external billing; only local disk/compute for stored traces).

### Local LLM tracing (`backend/app/tracing.py`)

A lighter-weight complement to Phoenix for when you don't want a collector running: set `VOYAGER_TRACE_LLM=1` to log every non-streaming LLM call (full messages in, content/tool-calls out) as one JSON line to `VOYAGER_TRACE_PATH` (default `./trace_log.jsonl`). Off by default; both this and Phoenix can be on at once. Each entry carries `context` (the existing `usage_context` label: `chat`/`planning`/`eval_judge`/...) and `node` — a finer-grained label set by each LangGraph node function (`load_context`, `classify_intent`, `build_brief`, `activities_researcher`, `food_researcher`, `logistics_researcher`, `accommodation_researcher`, `optimizer`, `critic`, `clarify`, `assemble_reply`) right before it calls the LLM, via the `node_context` contextvar. Useful for safety-eval forensics — e.g. filtering to `node=build_brief` to check whether an injected instruction survives that node's summarization step (see `docs/safety-evals-spec.md`).

## Cost & token accounting (`backend/app/usage.py`)

The OpenRouter client is wrapped once in `app/claude.py`; every call logs model, tokens, and OpenRouter-reported cost (`usage: {include: true}` — no local price table) to the `usage_log` table with a context label: `chat`, `planning`, `memory_extraction`, `eval_judge`. Recording is fail-open; streaming calls pass through unrecorded.

Endpoints: `GET /api/usage/summary?days=30`, `GET /api/usage/recent?limit=50`; surfaced in the UI's Usage tab.

Month 6 will build per-user rate limits and LLM budget quotas on top of this.
