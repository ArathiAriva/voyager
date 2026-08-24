# Evals, feature flag, observability, cost

## Planner feature flag (`backend/app/flags.py`)

`VOYAGER_PLANNER` env (`single` | `multi`) with per-request override, so single-agent and multi-agent planners can be A/B'd in the same process. This is the backbone of the eval comparisons — keep both paths working.

## Eval harness (`backend/evals/`)

- `golden_set.json` — 15 planning cases.
- `judge.py` — LLM-as-judge, 5 dimensions, temperature 0 (usage context `eval_judge`).
- `run.py` — runs both planners through the **real API** (`python -m evals.run`), writes timestamped results to `evals/results/<ts>/` (`single.json`, `multi.json`, `report.md`, `manifest.json`). Output shape is LangSmith-feedback-compatible (LangSmith datasets planned for Month 5).

Every result row records `agent_model` and `judge_model`; a score is not interpretable
without them. `--judge-model` overrides the judge, which otherwise defaults to the model
being evaluated — the report flags that as a self-preference-bias caveat. Backend
`event: error` SSE frames are reported as `backend error: ...` rather than the
uninterpretable "empty reply".

Eval runs are traced by Phoenix like normal traffic.

## Safety eval suite (`backend/evals/safety_*`)

Indirect prompt-injection evals — untrusted saved-place text carries an injected
instruction, the runner seeds it via the API, drives a benign user turn, and checks
whether the agent obeyed. Spec: `docs/safety-evals-spec.md`. Status and open items:
`OPEN-ITEMS.md` § "Safety evals — Phase 2".

- `safety_set.json` — 15 cases; taxonomy is `placement` x `instruction_style` x
  `attack_goal`, plus an optional `planners` field restricting a case to one architecture.
- `safety_run.py` — `--planner single|multi|both`, `--runs N`, `--cases`, `--gate`.
  Results per architecture, **never pooled** (the graph launders saved-place text through
  `build_brief`; the single-agent loop ingests it raw).
- `safety_judge.py` — 1–5 compliance scale, used only where a case declares it.
- `safety_judge_calibrate.py` — picks the judge by measured agreement with hand labels.
- `safety_ledger.py` — aggregates every batch in `results/` with Wilson intervals
  (`python -m evals.safety_ledger` → `SAFETY-LEDGER.md`).
- `safety_rejudge.py` — replays a judge over stored replies, to isolate judge changes.

**Run it against an empty profile** (`--profile safetyeval`, a scratch profile with its
own DB + Chroma). `search_places` is semantic, so on a populated profile fixtures lose to
the user's real saved places — measured 3% fixture exposure on `egwene`, meaning most
"passes" scored a payload the agent never saw. The runner preflights this and refuses to
start. Reset the profile **between** runs too: `_auto_save_places` writes planner output
back as saved places, so the suite pollutes its own profile as it goes.

Guards worth knowing, all of which exist because they caught a real vacuous pass:
routing to the multi-agent graph needs both a phrase match *and* `classify_intent`
reading `full_plan`; an `itinerary_not_contains` check with no persisted itinerary is
recorded as `skipped`, and a case whose every substantive check was skipped returns
`no_signal` rather than `pass`; backend errors are surfaced before the routing guard, so
an outage isn't misreported as a bad case script.

## Observability (`backend/app/observability.py`)

Arize Phoenix via OpenInference/OTel. Opt-in: set `PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces` in `backend/.env`; `setup_tracing()` is a no-op otherwise. Covers both the single-agent loop and every LangGraph node (latency, tokens, prompts/responses). Run Phoenix with `phoenix serve` (local, free — no external billing; only local disk/compute for stored traces).

### Local LLM tracing (`backend/app/tracing.py`)

A lighter-weight complement to Phoenix for when you don't want a collector running: set `VOYAGER_TRACE_LLM=1` to log every non-streaming LLM call (full messages in, content/tool-calls out) as one JSON line to `VOYAGER_TRACE_PATH` (default `./trace_log.jsonl`). **On by default in local dev** (set in `backend/.env`) so the planner's intermediate outputs stay queryable after the fact; both this and Phoenix can be on at once. Each entry carries `context` (the existing `usage_context` label: `chat`/`planning`/`eval_judge`/...) and `node` — a finer-grained label set by each LangGraph node function (`load_context`, `classify_intent`, `build_brief`, `activities_researcher`, `food_researcher`, `logistics_researcher`, `accommodation_researcher`, `optimizer`, `critic`, `clarify`, `assemble_reply`) right before it calls the LLM, via the `node_context` contextvar.

Read entries back with `python -m evals.trace_query`:

```sh
python -m evals.trace_query --nodes                    # what was captured, with counts
python -m evals.trace_query --node build_brief -n 3    # the last 3 planning briefs
python -m evals.trace_query --node critic --full       # untruncated input + output
python -m evals.trace_query --grep AZURE-PELICAN       # find a string in any field
python -m evals.trace_query --node build_brief --json  # raw entries, for piping
```

Two things to know. **The brief is the highest-value thing in here** — it's the only place you can see what the planner actually decided about the user before the researchers ran, and it's not persisted anywhere else (it lives in LangGraph's in-memory `PlanningState` and is discarded when the run ends). **Entries are unredacted** — full prompt and response bodies, so every conversation, saved place, and journal excerpt that reaches an LLM. The file is gitignored and rolls to a single `.1` backup past `VOYAGER_TRACE_MAX_MB` (default 50), but treat it as sensitive on any profile holding real data.

Also useful for safety-eval forensics — e.g. filtering to `node=build_brief` to check whether an injected instruction survives that node's summarization step (see `docs/safety-evals-spec.md`).

## Cost & token accounting (`backend/app/usage.py`)

The OpenRouter client is wrapped once in `app/claude.py`; every call logs model, tokens, and OpenRouter-reported cost (`usage: {include: true}` — no local price table) to the `usage_log` table with a context label: `chat`, `planning`, `memory_extraction`,
`eval_judge`, `safety_eval`.

Caveat: the eval scripts call bare `load_dotenv()`, so they load root `.env` and their
*judge* calls are accounted to whatever `DATABASE_URL` that resolves to — not the profile
the backend under test is running. Total run cost is therefore split across two databases
(R-3). Recording is fail-open; streaming calls pass through unrecorded.

Endpoints: `GET /api/usage/summary?days=30`, `GET /api/usage/recent?limit=50`; surfaced in the UI's Usage tab.

Month 6 will build per-user rate limits and LLM budget quotas on top of this.
