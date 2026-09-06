# Multi-agent trip planning (LangGraph)

Full design doc: [docs/multi-agent-planning.md](../docs/multi-agent-planning.md). Code: `backend/app/planning/` (graph) and `backend/app/agents/` (nodes).

## Routing

`app/planning/router.py`:
- `is_planning_request(text)` — substring match against `_PLANNING_PHRASES` ("plan my", "itinerary", "days in", …) and `_REVISION_PHRASES` ("find cheaper restaurants", "change day", …), **plus a shape rule** for revisions the phrase list misses: a day reference (`day 3`, `the second day`, `morning`/`afternoon`/`evening`) **and** an edit verb (`add`, `swap`, `drop`, `instead`, …) both present.

  Both halves are required, so "what did I do on day 2?" stays a question while
  "make day 2 more relaxed" routes to the graph. This matters more than it looks:
  a revision that misses the router falls through to the single-agent loop, where
  `set_itinerary` replaces the *entire* itinerary — so under-matching risks losing
  days. Measured against natural phrasings the phrase list alone caught 2 of 8;
  with the shape rule, 7 of 8 with no false positives on a question/chit-chat set.
  The remaining miss uses a weekday ("more time downtown on Friday") rather than a
  day number; matching weekdays was rejected as too false-positive-prone, and the
  `set_itinerary` guard is the backstop.
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
- **The brief carries `current_trip` when a trip is underway** (`find_live_trip`, Live Trip Mode Stage 3). A mid-trip replan must start from where the user actually is — without it the graph plans the remaining days as though the trip had not begun, suggesting a day 1 arrival on day 3. `BRIEF_PROMPT` instructs the model to use its destination and set `duration_days` to the days that *remain*. The key is absent rather than null when nothing is live.
