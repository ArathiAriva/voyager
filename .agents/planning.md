# Multi-agent trip planning (LangGraph)

Full design doc: [docs/multi-agent-planning.md](../docs/multi-agent-planning.md). Code: `backend/app/planning/` (graph) and `backend/app/agents/` (nodes).

## Routing

`app/planning/router.py`:
- `is_planning_request(text)` — substring match against `_PLANNING_PHRASES` ("plan my", "itinerary", "days in", …) and `_REVISION_PHRASES` ("find cheaper restaurants", "change day", …).
- `run_planning_graph(user_message, session, trip_id, emit_step)` — builds the initial `PlanningState` and calls `planning_graph.ainvoke`; the DB session and an `emit_step` callback (SSE progress labels) are passed via LangGraph `config["configurable"]`.

Non-planning messages never touch the graph. Graph failure falls back to the single-agent loop in `routers/conversations.py`.

## Graph shape (`planning/graph.py`, state in `planning/state.py`)

```
classify intent ──▶ (clarifying question if vague — stops early)
      │
      ▼
planner: gather context (search_memory, search_places, get_trips) + build brief
      │
      ▼  parallel researchers (scoped by revision_scope on revisions)
activities · food · accommodation · logistics
      │
      ▼
optimizer  — geospatial clustering/sequencing by `area` of places
      │
      ▼
critic     — scores plan (critique_score), flags issues; low score loops back
      │
      ▼
assemble   — persist itinerary (set_itinerary), auto-save recommended places, write final_reply
```

## PlanningState keys worth knowing

`user_message`, `trip_id`, `revision_scope` (`{domains, day_range, instruction}` — revisions re-run only affected researchers, e.g. "find cheaper restaurants" → food only), `brief`, per-domain result lists, `itinerary_draft`, `unplaced_items`, `conflicts`, `critique_score`/`critique_issues`, `revision_count`, `missing_info`, `final_reply`.

## Agents (`app/agents/`)

| File | Role |
|---|---|
| `planner.py` | Orchestrator: intent parsing, brief building, context gathering |
| `activities.py` / `food.py` / `accommodation.py` / `logistics.py` | Domain researchers, run in parallel |
| `optimizer.py` | Geospatial optimizer — clusters days by neighbourhood (`area` column on saved places) |
| `critic.py` | Scores the draft; drives the revision loop |

Per-agent model selection is supported (optional `model=` threaded through agent LLM calls).

## Side effects

- Itinerary persisted to the trip's JSON `itinerary` column (`ItineraryDay` includes `area_focus` and `accommodation`).
- All LLM-recommended places are auto-saved to Saved Places with Google Maps links after planning completes.
- Each node emits a step label surfaced live in the chat UI via SSE.
