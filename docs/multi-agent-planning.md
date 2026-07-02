# Multi-Agent Trip Planning — Design Doc

**Status:** Design validated against codebase — ready to implement  
**Target phase:** Month 4  
**Prerequisite:** Existing single-agent loop in `backend/app/routers/conversations.py` and tool executor in `backend/app/tools.py`

### Schema changes required (validated 2026-07-01)

The design was validated against the current code. Four gaps were found and resolved:

| Gap found | Resolution |
|---|---|
| `SavedPlaceORM` has no `area`/`neighbourhood` field — optimizer needs it to cluster | **Add nullable `area` column** to `SavedPlaceORM` + migration; populate via enrichment and `save_place` tool |
| `ItineraryDay` has only `day/date/title/plan` — no `area_focus`/`accommodation` | **Extend `ItineraryDay`** pydantic schema with `area_focus` and `accommodation` (no DB migration — `itinerary` is already a JSON column) |
| `ConversationORM` has no `trip_id` link | **No schema change** — Planner calls `get_trips`, matches by destination, passes `trip_id` to `set_itinerary`, mirroring the current agent |
| `TOOL_SCHEMAS` is a **list**, not a dict; `get_model()` reads model from env at startup with no per-call override | Add a `tool_by_name()` lookup helper; thread an optional `model=` param through agent LLM calls for per-agent model selection |

---

## Problem with the current architecture

The current agent is a generalist. When a user says "plan my 7 days in Japan", a single LLM call:
- Searches memory
- Looks up saved places
- Generates activities, accommodation, food, logistics
- Writes the itinerary
- Calls `set_itinerary` to save it

This works for simple cases. It breaks down because:
- **No parallelism** — research happens sequentially, so a rich plan takes many serial LLM calls
- **No specialization** — a generalist balances food, logistics, and activities simultaneously, doing each worse than a focused agent would
- **No spatial reasoning** — itineraries don't account for geography (putting lunch on the opposite side of the city from the morning activity)
- **No optimization** — accommodation isn't chosen relative to where the user will actually be spending time
- **No critique** — the plan is never stress-tested before being shown to the user

---

## Proposed architecture

```
User message
     │
     ▼
┌─────────────────────────────────────┐
│           Planner Agent             │  ← orchestrator; owns the conversation
│  - parses intent                    │
│  - builds research brief            │
│  - dispatches researcher agents     │
│  - runs Geospatial Optimizer        │
│  - sends draft to Critic            │
│  - assembles final itinerary        │
│  - calls set_itinerary tool         │
└──────────────┬──────────────────────┘
               │  dispatches in parallel
    ┌──────────┼──────────────┐──────────────┐
    ▼          ▼              ▼              ▼
Activities  Food &       Accommodation   Logistics
Researcher  Drink        Researcher      Researcher
            Researcher
    │          │              │              │
    └──────────┴──────────────┴──────────────┘
               │  structured results
               ▼
        Geospatial Optimizer
        (clusters & sequences by location)
               │
               ▼
          Critic Agent
          (scores plan, flags weak spots)
               │
               ▼
        Planner assembles final reply
```

---

## Agents

### Planner (orchestrator)

**Role:** The only agent the user talks to directly. Owns the conversation state, coordinates all sub-agents, and produces the final output.

**Responsibilities:**
- Parse the user's intent into a structured planning brief (destination, dates, travel style, constraints)
- Search user memory (`search_memory`) and saved places (`search_places`) before dispatching researchers — so researchers receive personal context
- Build per-researcher task briefs (what to find, constraints, user preferences relevant to that domain)
- Dispatch researchers in parallel
- Pass their outputs to the Geospatial Optimizer
- Send the optimized draft to the Critic
- Incorporate Critic feedback (loop back to researchers if score is too low, otherwise proceed)
- Call `set_itinerary` to persist the final plan
- Write a warm, concise summary reply to the user

**System prompt emphasis:**
- Decomposition and delegation
- Never fills in research details itself — always waits for researcher outputs
- Understands the output schema each researcher must return

**Tools available:**
- `search_memory`, `get_trips`, `search_places`, `search_journal`
- `set_itinerary`, `create_trip`, `update_trip`
- Internal: `dispatch_researchers`, `run_optimizer`, `run_critic`

---

### Activities Researcher

**Role:** Finds attractions, experiences, day trips, and things to do at the destination.

**Responsibilities:**
- Receive: destination, travel dates, user interests/style from memory, saved places tagged as `attraction` or `neighbourhood`
- Research: must-see vs off-the-beaten-path split, opening hours, booking requirements, crowd patterns by day/time
- Output: ranked list of activities with name, category, area/neighbourhood, estimated duration, best time of day, notes

**System prompt emphasis:**
- Prioritize based on user's stated interests (passed in context)
- Flag any activities that require advance booking
- Include at least one "local/hidden gem" option if destination warrants it

**Tools available:**
- `search_places` (scoped to `attraction`, `neighbourhood`)
- `get_weather` (MCP) — to flag outdoor activities affected by weather
- Web search (when added in a future phase)

---

### Food & Drink Researcher

**Role:** Finds restaurants, cafes, bars, street food, and market experiences.

**Responsibilities:**
- Receive: destination, travel dates, dietary preferences from memory, saved places tagged as `restaurant`, `cafe`, `bar`
- Research: meal options per day (breakfast / lunch / dinner), with area tag for each so the optimizer can co-locate with activities
- Output: list of food options with name, meal type, area/neighbourhood, cuisine, price tier, notes, whether reservation needed

**System prompt emphasis:**
- Always tag each recommendation with an area so the optimizer can match food to nearby activities
- Prioritize user's saved places first, supplement with new recommendations
- Flag reservation-required spots clearly

**Tools available:**
- `search_places` (scoped to `restaurant`, `cafe`, `bar`)
- Web search (future)

---

### Accommodation Researcher

**Role:** Recommends where to stay, optimized for convenience to the overall itinerary.

**Responsibilities:**
- Receive: destination, dates, user accommodation preferences from memory, saved places tagged as `hotel`, budget signal
- This researcher runs **after** Activities and Food researchers — it receives their outputs to pick the area with the highest density of planned activities
- Research: 2–3 accommodation options across different tiers/styles, with area and proximity notes
- Output: ranked options with name, area, price tier, why it's convenient for the planned itinerary

**System prompt emphasis:**
- Use the activity and food clusters from other researchers to recommend the most central area
- If trip spans multiple cities or areas, consider whether a hotel move mid-trip makes sense
- Surface user's saved hotels first

**Tools available:**
- `search_places` (scoped to `hotel`)
- Receives activity/food researcher outputs as context (passed by Planner)

---

### Logistics Researcher

**Role:** Handles transport, timing, and practical day-to-day movement.

**Responsibilities:**
- Receive: destination, activity list with areas from other researchers
- Research: airport transfers, intercity transport (train/bus/ferry), local transport options (metro, walking, taxis), typical travel times between key areas
- Output: transport notes per day segment, timing constraints, cost estimates, booking requirements

**System prompt emphasis:**
- Think about transitions — if Day 3 activity ends in area A and Day 4 starts in area B, flag the transfer
- Surface any transport that needs advance booking (Shinkansen, ferries, etc.)
- Don't generate a full itinerary — just transport/timing constraints that the optimizer uses

**Tools available:**
- `get_weather` (MCP) — weather affects transport choices
- Web search (future)
- Receives activity list from Planner as context

---

### Geospatial Optimizer

**Role:** Not a conversational agent — a pure function (or a tightly-prompted LLM call) that takes all researcher outputs and arranges them into a coherent day-by-day sequence.

**Responsibilities:**
- Cluster activities, food, and accommodation by area/neighbourhood
- Sequence each day to minimize cross-city travel (morning in area A → lunch in area A → afternoon in area A)
- Assign food recommendations to days and meal slots, co-located with that day's activities
- Flag conflicts (e.g. two must-do activities on the same day that are geographically far apart)
- Output: a structured day-by-day plan matching the `ItineraryDay` schema

**Implementation note:** This is the hardest agent to build well without real map data. In Month 4, approximate with neighbourhood-level clustering (just string matching on area names). In a later phase, wire up a geocoding API and do actual distance calculations.

---

### Critic Agent

**Role:** Reads the optimized draft itinerary and scores it before it reaches the user.

**Responsibilities:**
- Check internal consistency: does Day 3 logistically follow Day 2?
- Check user preference alignment: does the plan reflect what's in memory (e.g. user dislikes touristy spots)?
- Check coverage: are all saved/bookmarked places incorporated if relevant?
- Check pacing: is there breathing room, or is every hour scheduled?
- Output: score (1–5) + list of specific issues with suggested fixes

**Planner behaviour based on Critic output:**
- Score 4–5: proceed, optionally surface top issues as "things to watch" in the reply
- Score 2–3: loop — send issues back to relevant researchers for targeted fixes, re-optimize, re-critique (max 2 loops)
- Score 1: surface to user honestly — "I had trouble building a strong plan for this; here's what I have so far"

**System prompt emphasis:**
- Be specific in feedback — "Day 4 lunch is 4km from the morning activity, consider moving to Shinjuku instead" not "improve geography"
- Don't rewrite the plan — just score and annotate

---

## Communication protocol

Agents communicate via **structured JSON messages** passed by the Planner. Each message has a type, sender, and payload.

### Planning brief (Planner → Researchers)

```json
{
  "type": "planning_brief",
  "destination": "Kyoto, Japan",
  "dates": "April 10–17 2025",
  "duration_days": 7,
  "user_context": {
    "preferences": ["boutique hotels", "street food", "avoids crowds"],
    "past_trips": ["Tokyo 2023", "Osaka 2022"],
    "saved_places": [
      {"name": "Ichiran Ramen", "category": "restaurant", "area": "Shinjuku"},
      {"name": "Fushimi Inari", "category": "attraction", "area": "Fushimi"}
    ]
  },
  "constraints": {
    "budget": "mid-range",
    "dietary": [],
    "mobility": null,
    "must_include": []
  }
}
```

### Researcher output (Researcher → Planner)

```json
{
  "type": "research_result",
  "agent": "activities_researcher",
  "items": [
    {
      "name": "Arashiyama Bamboo Grove",
      "category": "attraction",
      "area": "Arashiyama",
      "duration_hours": 2,
      "best_time": "morning",
      "notes": "Go before 8am to avoid crowds",
      "booking_required": false,
      "priority": "high"
    }
  ]
}
```

### Optimizer input (Planner → Optimizer)

```json
{
  "type": "optimizer_input",
  "duration_days": 7,
  "activities": [ /* from activities researcher */ ],
  "food": [ /* from food researcher */ ],
  "accommodation": { /* from accommodation researcher */ },
  "logistics": { /* from logistics researcher */ }
}
```

### Optimizer output (Optimizer → Planner)

```json
{
  "type": "itinerary_draft",
  "days": [
    {
      "day": 1,
      "date": "2025-04-10",
      "area_focus": "Arashiyama",
      "title": "Arrival & Arashiyama",
      "accommodation": "The Screen Kyoto",
      "plan": "Morning: Bamboo Grove (arrive early). Lunch: Shoraian tofu restaurant nearby. Afternoon: Tenryu-ji garden. Evening: check-in, dinner in Gion."
    }
  ],
  "unplaced_items": ["Nishiki Market — no slot found, suggest adding a Day 8"],
  "conflicts": ["Fushimi Inari and Arashiyama are both high-priority but 40 min apart — split across two days"]
}
```

### Critic output (Critic → Planner)

```json
{
  "type": "critique",
  "score": 4,
  "issues": [
    {
      "day": 3,
      "severity": "minor",
      "description": "Lunch spot is 3km from morning activity. Consider moving to Pontocho instead.",
      "suggestion": "Swap lunch to Pontocho Alley — same cuisine, walkable from Gion."
    }
  ],
  "overall_notes": "Good pacing. Saved places well-integrated. Day 5 is slightly overloaded."
}
```

---

## Partial execution and revision

The graph must support running only a subset of researchers — both for focused initial requests ("just find me food options") and for user-driven revisions ("actually find cheaper restaurants", "change Day 3 to temples").

### RevisionScope

The Planner populates a `revision_scope` at the start of every run. For a full fresh plan it covers all domains; for a revision it narrows to only the affected researchers.

```python
class RevisionScope(TypedDict):
    domains: list[Literal["activities", "food", "accommodation", "logistics"]]
    day_range: tuple[int, int] | None  # None = whole trip; (3, 3) = Day 3 only
    instruction: str  # user's revision request in natural language
```

**Examples:**

| User message | `domains` | `day_range` |
|---|---|---|
| "Plan my 7 days in Kyoto" | all | None |
| "Find cheaper restaurants" | `["food"]` | None |
| "Change Day 3 to focus on temples" | `["activities"]` | `(3, 3)` |
| "Find accommodation closer to Gion" | `["accommodation"]` | None |
| "Redo the whole last 3 days" | all | `(5, 7)` |

### Persisting between runs

The existing `itinerary` JSON column on `TripORM` is the source of truth for revision runs. When a researcher domain is **not** in `revision_scope.domains`, the graph skips that node and loads its prior output from the persisted itinerary instead. This means:

- Only re-run what changed
- Optimizer always runs (it needs to re-sequence even if only food changed)
- Critic always runs
- Accommodation re-runs automatically if activities changed (it depends on area clusters)

### Revision flow

```
User revision message
     │
     ▼
[load_user_context]
     │
     ▼
[classify_revision]        ← Planner LLM: extract RevisionScope from message
     │                        loads existing itinerary from TripORM as baseline
     │
     ├── activities in scope? ──▶ [activities_researcher]  ─┐
     ├── food in scope?       ──▶ [food_researcher]          │  only scoped researchers run
     ├── logistics in scope?  ──▶ [logistics_researcher]     │
     └── skip → load from DB ──────────────────────────────┘
     │
     ▼
[accommodation_researcher]  ← always re-runs if activities changed (area dependency)
     │                         otherwise loads from DB
     ▼
[geospatial_optimizer]      ← always runs; merges new + unchanged researcher outputs
     │
     ▼
[critic] → [assemble_reply] → [persist_itinerary]
```

---

## LangGraph integration

### Why LangGraph

The Planner needs to:
1. Fan out to N researchers in parallel
2. Wait for all to return
3. Conditionally loop (if Critic score is low)
4. Conditionally skip nodes based on `revision_scope`
5. Maintain state across all of this — including across revision turns

LangGraph handles this natively with nodes, conditional edges, the `Send` API for parallel fan-out, and checkpointing for durable state between user turns. The alternative (custom asyncio orchestration) would require rebuilding all of that.

### Graph structure

```
START
  │
  ▼
[load_user_context]        ← fetch memory, trips, saved places; load existing itinerary if revision
  │
  ▼
[classify_intent]          ← Planner LLM: full plan vs revision; populate RevisionScope
  │
  ▼ (conditional fan-out via Send API — only domains in revision_scope)
  ├──▶ [activities_researcher]  ─┐
  ├──▶ [food_researcher]         │  parallel, selective
  ├──▶ [logistics_researcher]    │
  └──▶ (skip → load from DB) ───┘
  │
  ▼
[accommodation_researcher] ← runs if activities changed or accommodation in scope;
  │                           otherwise loads from DB
  ▼
[geospatial_optimizer]     ← always runs; merges new + unchanged outputs
  │
  ▼
[critic]                   ← LLM call, outputs score + issues
  │
  ▼
[should_revise?]           ← conditional edge
  ├── score >= 4  ──▶ [assemble_reply]
  └── score < 4   ──▶ [targeted_revision]  ← re-scopes to only domains the Critic flagged
                         │
                         └──▶ [geospatial_optimizer] (loop, max 2x)
  │
  ▼
[assemble_reply]           ← Planner LLM: write user-facing summary
  │
  ▼
[persist_itinerary]        ← calls set_itinerary tool; saves full merged itinerary to TripORM
  │
  ▼
END
```

### Graph state schema

```python
class PlanningState(TypedDict):
    # Input
    user_message: str
    trip_id: str

    # Execution mode
    revision_scope: RevisionScope  # which domains/days to (re-)run

    # User context (loaded at start)
    user_preferences: list[str]
    saved_places: list[dict]
    past_trips: list[dict]

    # Existing itinerary (None for fresh plans; populated from TripORM for revisions)
    existing_itinerary: list[dict] | None

    # Planning brief
    brief: dict

    # Researcher outputs (each field: new output if researcher ran, else loaded from existing_itinerary)
    activities: list[dict]
    food: list[dict]
    logistics: dict
    accommodation: dict

    # Optimizer output
    itinerary_draft: list[dict]
    unplaced_items: list[str]
    conflicts: list[str]

    # Critic output
    critique_score: int
    critique_issues: list[dict]
    revision_count: int  # guard against infinite loops (max 2)

    # Final output
    final_reply: str
```

---

## Integration with existing Voyager backend

The multi-agent planner is **not a replacement** for the existing conversation loop — it's a parallel path that activates for trip planning requests.

### Routing

The existing `send_message` endpoint detects planning intent and routes accordingly:

```python
# In conversations.py send_message handler
if _is_planning_request(body.content):
    reply = await run_planning_graph(body.content, trip_id, session)
else:
    reply = await run_standard_agent_loop(body.content, history, session)
```

`_is_planning_request` can be a simple keyword check initially ("plan", "itinerary", "7 days in") — upgrade to an LLM classifier later if needed.

### Preserving existing tools

Researchers are just LLM calls with a constrained set of tools — they reuse `TOOL_SCHEMAS` and `execute_tool` from `tools.py`. No new tool infrastructure needed.

### Streaming

Each researcher output can be streamed to the frontend as a progress update, so the user sees:
```
🔍 Researching activities in Kyoto...
🍜 Finding food recommendations...
🏨 Selecting accommodation...
📍 Optimizing your route...
✅ Plan ready
```

This is a frontend concern (SSE or websocket) — the graph nodes emit progress events the existing UI can render.

---

## What's deferred

| Feature | Reason |
|---|---|
| Real geocoding (lat/lng distance) | Needs a maps API; neighbourhood-level approximation sufficient for Month 4 |
| Web search for researchers | Needs a search API integration; use saved places + memory as data sources first |
| Telegram/email trip briefs | Nice input surface for Logistics agent; defer to Month 6 |
| User-facing critique transparency | Showing the Critic's reasoning is a UI feature; internal-only for now |
| Per-researcher streaming | Needs SSE infrastructure changes; ship with a single "planning..." indicator first |

---

## Open questions

1. **Model per agent:** Use the same model for all agents (simplest), or use a cheaper/faster model for researchers and a stronger one for Planner and Critic? OpenRouter makes this trivial to experiment with.

2. **When to trigger:** Keyword detection vs LLM intent classifier for routing to the planning graph. Keyword is fast and cheap; classifier is more reliable but adds latency. `classify_intent` node doubles as the classifier — no separate routing step needed.

3. **User confirmation before persisting:** Should the Planner show the itinerary draft and ask "Save this?" before calling `set_itinerary`? Consistent with existing `create_trip` UX — probably yes.

4. ~~**Partial plans**~~ **Resolved:** `RevisionScope` handles this. Fresh partial requests (e.g. "just find me food options") set only `["food"]` in domains with no existing itinerary. The graph runs only the food researcher, skips optimizer sequencing (nothing to sequence against), and returns food options as a list rather than a full itinerary.

5. ~~**Re-planning**~~ **Resolved:** `RevisionScope` + `existing_itinerary` from `TripORM` handle this. The `classify_intent` node extracts the scope; only affected researchers re-run; unchanged outputs are loaded from the persisted itinerary; the optimizer re-sequences the merged result.
