# Voyager — AI Travel Companion

## Vision

Voyager is an AI-native solo travel companion that understands not just where you want to go, but *how* you travel and what travel means to you. It remembers your past trips, learns your preferences, helps you plan with intelligence, and reflects your journey back to you over time.

> "An AI that augments human meaning-making through travel."

---

## What Voyager Does

- **Plan** — Generate itineraries tailored to your travel style, not generic tourist routes
- **Remember** — Build a personal memory of your trips, preferences, and reflections
- **Research** — Dispatch agents to gather real-time info on places, weather, and logistics
- **Reflect** — Surface patterns in how you travel and what you value
- **Recommend** — Suggest destinations, experiences, and media based on your history

---

## Phases

Phases, not months — the calendar slipped and the *shape* of the work is what matters.
Each phase is a capability that deepens over time rather than a box that closes.

| Phase | Theme | Status |
|---|---|---|
| **1. Core architecture** | Agent loop, tool calling, MCP, memory, RAG, multi-agent planning | ✅ Built |
| **2. Operability** | Eval harness, feature flag, tracing, cost accounting | ✅ Built, ongoing |
| **3. Trustworthiness** | Agent safety evals — indirect prompt injection, both architectures | ⏸ Paused 2026-09-03 — suite and results intact, resumes later |
| **4. Observability of retrieval** | Retrieval quality monitoring — the unmeasured RAG layer | 🔄 Instrumentation + UI built; golden set gated on traffic |
| **5. Memory maturity** | Preference provenance → dedup → reconciliation → evolution | 🔄 Provenance, dedup and reconciliation built; evolution unscheduled |
| **Live Trip Mode** | Agent knows a trip is underway: which day, today's plan | ✅ Built (Stages 1, 3, 4) — Stage 2 columns unbuilt |
| **Trip-scoped chats** | Conversations carry a `trip_id`; picker on new chat | ✅ Built (all 4 stages) |
| **Visited places & anecdotes** | Mark a saved place as visited; store the user's own note about it | ✅ Built (Stages 1–3) — chat capture unbuilt |
| **Conditional preferences + onboarding** | Preferences carry *when* they hold; onboarding asks about contrasting trips | 🕐 Candidate — design only, unscheduled |
| **6. Production** | Deployment, auth, Postgres/pgvector, rate limits, quotas | 🔄 **Partial** — deployment + a shared-token lock, for one real trip. The rest deferred |

**Deviation worth naming (2026-09-05):** Live Trip Mode, trip-scoped chats, and
visited places/anecdotes were built while Phase 4 was still "Next". Guiding
principle 2 says not to build ahead of the phase, and this did. Two mitigations,
neither a full defence: each began from a *bug* found in the current work (B-13's
duplicate trips, B-14's lost extractions), and Phase 4's remaining step is gated on
live traffic rather than effort — the golden set needs real queries to label, and
`retrieval_log` holds almost none. Using the app is what unblocks it.

Phases 2–4 are the *maintenance* spine: an LLM app gradually builds sophistication in
measuring itself, and each layer exposes problems the previous one couldn't see. Cost
accounting made spend visible; tracing made intermediate agent state visible; safety evals
made injection resistance measurable; retrieval monitoring is the missing piece —
everything so far judges final replies, so a bad plan can't be attributed to a bad
retrieval versus a bad LLM.

### Phase detail

#### Phase 1 — core architecture (built)

**Memory & journal**

- [x] Episodic memory — per-conversation summaries stored in Chroma, retrieved via `search_memory` tool
- [x] Semantic memory — distilled user preferences extracted post-conversation and embedded in Chroma
- [x] Memory retrieval — agent proactively searches memory before answering personalisation-relevant queries
- [x] Trip journal entries — freeform notes per trip, date-stamped, multi-source (app / telegram / email)
- [x] Connected content — attach photos, Instagram, TikTok, blog links to a trip
- [x] Memory views — dedicated UI page surfacing episodic and semantic memories
- [x] Active trip status — trips can be marked active; distinct badge + card styling
- [x] Itinerary generation + storage — agent can plan and persist a day-by-day itinerary per trip; Itinerary tab in UI
- [x] Multi-profile support — per-user SQLite + Chroma, switchable via `--profile` flag
- [x] LLM-generated seed data — realistic profiles for development and testing
- [ ] Preference evolution — moved to Phase 5 and still unscheduled, but **no longer blocked**: M-2 provenance shipped 2026-09-04. It now waits on enough real usage for genuine change to be distinguishable from extraction noise

**Live Trip Mode** — **Stages 1, 3 and 4 built 2026-09-05**. Design:
[docs/live-trip-mode.md](docs/live-trip-mode.md).

- [x] Stage 1 — trip temporality (`app/live_trip.py`), `get_current_trip` tool,
      system-prompt injection while a trip is underway. No migration: itinerary
      days already carry ISO dates, so any planned trip is live-capable today.
- [ ] Stage 2 — `start_date`/`end_date` columns + date picker (needs Alembic).
      **Deliberately skipped**: Stage 1 covers any trip with an itinerary, so the
      columns only help trips never planned in-app — a migration for a narrow case.
- [x] Stage 3 — planner brief carries the live trip, so a mid-trip replan plans only
      the days that remain. The journal half was already done (trip from the URL,
      date defaulting to today); only **chat capture** remains, and it is gated on
      the verbatim-mechanism decision below rather than on effort.
- [x] Stage 4 — "Day 2 of 4" badge on the trip card and detail page. Pulled forward,
      because Stage 1 created the inconsistency itself: the agent knew the user was
      on day 2 while the card still read "upcoming".

Liveness is **derived on read, never stored** — the pre-existing `status = "active"`
was decorative and went stale, which is the bug this avoids rather than repeats.

**Known limitation:** "today" is the server's local date, correct for a single-user
local app and wrong once deployed across timezones.

**Trip-scoped chats** — **built 2026-09-05** (all four stages). Design:
[docs/trip-scoped-chats.md](docs/trip-scoped-chats.md).

Conversations now carry a nullable `trip_id`, set from a picker on new chat (a live
trip preselects) or changed in the chat header. This began as a bug fix: the
planner's `_resolve_trip_id` **silently created a duplicate trip** whenever its
fuzzy destination match missed (B-13), because it had nothing but a destination
string to work with.

Still open — open question 2: carrying `trip_id` into **preference extraction**,
which is the exact missing back-reference behind **B-2** and **M-5**. Deliberately
not tacked onto the UI work: which preferences are destination-conditional versus
durable is a design decision, not plumbing. Probably the highest-value memory item
left.

**Visited places & anecdotes** — **Stages 1–3 built 2026-09-05**; chat capture not
built. Design: [docs/visited-places-and-anecdotes.md](docs/visited-places-and-anecdotes.md).

A saved place cannot be marked as visited, so a restaurant you booked and loved and
one you bookmarked and skipped are the same row. And the only user-writable text on
a place is `notes` — which on `egwene` is agent-written on all 73 places, and is a
documented prompt-injection channel. There is nowhere for "the queue was 40 minutes
but the mosaics were worth it" to go.

Both gaps have one shape: room for what Voyager *suggests*, none for what the user
*experienced*. It is also the only feedback edge in the app — Voyager plans a trip,
the user takes it, and nothing flows back.

Places carry a `visited` flag that retrieval can filter on, and `place_anecdotes`
holds the user's own words in their own Chroma collection — separate from the place's
description, because "what this place is" and "what happened to me there" are
different questions.

**Chat capture (Stage 4) is gated on a decision, not on effort:** the agent must
never author or edit anecdote or journal text, so capture needs either echo-back
before writing or a client-side path that never routes the text through the model.

Open question 1 is still open and still the one to weigh: "went to and wrote warmly
about" is the strongest preference signal available, and the extractor cannot see it.

**Conditional preferences + onboarding** — candidate, not scheduled. Design:
[docs/conversational-onboarding.md](docs/conversational-onboarding.md).

Started as onboarding (there is none today) and turned into something structural.
**Preferences are stored as unconditional facts about a person, and many of them are
not.** `travels solo` sits in memory beside `does not drink alcohol` as though both
are always true — but a family trip would *contradict* it, and M-4 would retire one.
Both are true. A trip with friends is a different trip from one with family or one
alone, and the model cannot say so.

**This subsumes M-5.** Destination scoping is one condition among several, and
probably not the strongest. It also corrects a conclusion nearly reached earlier —
that M-5 could be deferred because moiraine's 9 preferences contain nothing
destination-bound. Those 9 rows describe *one travel mode*, so the absence of
conflict was thin data, not evidence.

The doc maps what changes: storage is additive (Chroma is schemaless), extraction
changes shape in two call sites, **dedup and reconciliation must become
condition-aware or M-4 turns destructive**, and matching needs a condition on the
trip — the one Alembic migration required.

**RAG — journal + saved places**

- [x] Journal RAG — semantic search over journal entries via `search_journal` tool; Chroma embeddings auto-indexed on write
- [x] Saved places — save places (restaurants, hotels, neighbourhoods) from chat or manually; Jina Reader enrichment for summaries, OG thumbnail fetch, Chroma embeddings for RAG; agent tools `save_place` + `search_places`; Places tab with card grid and detail modal

**Multi-agent planning**

- [x] Multi-agent planning — LangGraph graph (`backend/app/planning/`) with specialist agents: planner, activities, food, accommodation, logistics, optimizer, critic; revision support scopes re-runs to affected domains
- [x] Intent routing — planning-phrase detection routes chat messages to the graph; non-planning messages stay on the single-agent loop
- [x] Streamed progress — graph nodes emit step labels surfaced live in the chat UI
- [x] Agent trace viewer — every planning run persisted to `planning_run` / `planning_step`, with a Traces page showing the per-agent timeline and each agent's full handoff (`/planning`)
- [x] Graceful fallback — graph failure falls back to the single-agent loop

#### Phase 2 — operability (built, ongoing)

- [x] Planner feature flag — `VOYAGER_PLANNER` env + per-request override (`app/flags.py`) to A/B single-agent vs multi-agent in the same process
- [x] Eval harness — 15-case golden set, LLM-as-judge (5 dimensions, temperature 0), runner comparing both planners through the real API with JSON results + markdown report (`backend/evals/`); output shape is LangSmith-feedback-compatible (kept because it costs nothing; adopting LangSmith itself was considered and dropped — Phoenix already covers tracing, and `safety_ledger.py` covers the cross-run aggregation that was the remaining draw)
- [x] Observability — Phoenix (OpenInference/OTel) tracing of both LLM paths; per-node latency, tokens, prompts (`app/observability.py`, opt-in via env)
- [x] Cost/token accounting — every LLM call logged with OpenRouter-reported cost and context label (chat / planning / memory / eval_judge); `/api/usage` endpoints + Usage tab in the UI

#### Phase 3 — trustworthiness (active)

Indirect prompt-injection eval suite. Not in the original plan; added as rung 0.5 of an
AI-safety transition track and scoped to extend Phase 2 rather than compete with later
work. Spec: [docs/safety-evals-spec.md](docs/safety-evals-spec.md). Live status:
[OPEN-ITEMS.md](OPEN-ITEMS.md) § "Safety evals — Phase 2".

- [x] Threat model traced in code — untrusted Jina-derived web content reaches planning
      agents via `saved_places`, which hold real tool access
- [x] Harness (`evals/safety_run.py`) — declarative cases, API-seeded fixtures,
      programmatic checks first with an LLM judge only where the failure is qualitative
- [x] 15 cases across payload placement, instruction style, and attack goal
- [x] Both architectures; results never pooled across them
- [x] Judge chosen by measured agreement with hand labels, not by reasoning
- [ ] **Run at n≥3 and publish** — the harness is trustworthy; the numbers are n=1

The honest lesson: most of the effort went into making the measurements *trustworthy*,
not into writing cases. Five separate defects each produced clean-looking results that
tested nothing. An eval that is wrong is worse than no eval, because it is believed.

#### Phase 4 — retrieval observability (steps 1–3 built; step 4 gated on traffic)

The RAG layer was entirely unmeasured. Both eval suites judge the final reply, so a bad
plan cannot be attributed to bad retrieval versus a bad LLM. Two retrieval bugs surfaced
by accident in one session (B-6: Rome plans retrieving Lisbon restaurants, live for
months; S-7: eval fixtures at 3% retrieval share, invalidating a phase of results). A
single recall metric would have caught both.

Design: [docs/retrieval-quality-spec.md](docs/retrieval-quality-spec.md). **Steps 1–3
are built**: always-on `retrieval_log` across all four collections, `GET
/api/retrieval/summary` and `/recent`, and a Retrieval page colour-graded against the
per-collection distance floors.

**Step 4 — the labelled golden set — is what remains, and it is gated on traffic
rather than effort.** `retrieval_log` holds almost no real rows, so labelling now
means guessing the query distribution, which is exactly what steps 1–3 were sequenced
to avoid. That instrumentation has already earned its keep: a single logged planning
query exposed both M-9 (retrieval padding results with non-matches) and M-10 (the
planner embedding raw logistics text against trait statements).

#### Phase 5 — memory maturity (steps 1–2 built 2026-09-04/05)

Sequenced, and the ordering was forced by dependencies:

1. ~~**M-2 — provenance.**~~ **Built.** `created_at`, `source` and `destination` on
   every preference and episode. It was the structural blocker under everything below.
2. ~~**M-3/M-4 — dedup and contradiction reconciliation.**~~ **Built.** Write-time
   dedup supersedes a near-duplicate's text; `app/reconcile.py` judges what distance
   cannot. Measuring the premise changed the design: a contradiction measures 0.303
   and an agreement 1.049, so no threshold separates them and a model has to decide.
3. **B-2's open half** — revoking preferences derived from an edited journal entry.
   Still open, and it did *not* fall out free as predicted: M-2 added `source` but
   not a per-entry back-reference, so nothing can identify which preferences came
   from a given entry. Wants the same `trip_id`/`entry_id` work as M-5.
4. **Preference evolution** — recency weighting, distinguishing genuine change from
   noise. Still deliberately unscheduled.

Evolution needs 1–3 shipped *and* enough real usage that contradictions accumulate
naturally; built earlier, there is no way to validate it. Phase 4's distance metrics
are the signal for when it becomes urgent.

#### Phase 6 — production (partially pulled forward 2026-09-06)

**A real Halifax trip on Sept 18–21 is the driver**, and phone access while travelling is
the one thing local-only cannot give. That justifies a *subset*, not the phase:

- [x] **Deployment** — Fly/Railway container + Vercel frontend (in progress)
- [x] **Auth** — but a **shared token** (`app/auth.py`), not the multi-tenant auth this
      phase means. Explicitly not a step toward it: multi-user is a *data isolation*
      problem here, and process-level isolation fails silently the moment one process
      serves two users. A login screen over that would look multi-user while pooling
      everyone's data.
- [ ] **Postgres/pgvector via Supabase** — deliberately skipped. SQLite and Chroma are
      fine at 27 saved places and 9 preferences, and migrating would mean recalibrating
      every distance threshold for a new embedding setup.
- [ ] **Multi-tenant auth** — needs `user_id` on every table and in every Chroma query
      first. Wants its own design pass, and it interacts with conditional preferences:
      both change how preferences are keyed, so the wrong order means migrating twice.
- [ ] **Per-user rate limits and budget quotas** — but **cap the OpenRouter key** before
      deploying regardless. Auth stops strangers; it does not stop a client-side loop.
- [ ] **CI as a regression gate**

The cost of this deviation is a **schema freeze while conditional preferences are
pending** — migrating a live database later rather than dev profiles. Accepted knowingly.

Measured beforehand, so the sizing is not guesswork: **~$0.17 per multi-agent itinerary,
$0.0036 per chat turn, $0.0011 per extraction**. The entire five-month build cost $5.34
across 1,219 calls. Hosting (~$6–11/month) dominates; LLM spend does not.

**Web only.** No native mobile — that is mobile engineering, not AI engineering, and must
not crowd out the phases above.

---

## Architecture & stack

See [README.md](README.md) — it carries the diagram, the component breakdown, and the
tech stack, and is the doc that has to stay correct for anyone actually running this.
Duplicating it here only creates two places to drift.

Decisions worth recording that the README doesn't cover:

- **Both planner paths stay alive.** The single-agent loop is not legacy to be deleted —
  it is the control arm for every A/B, and the only architecture where some failure modes
  (e.g. unconfirmed tool writes) are even expressible.
- **OpenRouter, not the Anthropic SDK, for now.** Model switching via `OPENROUTER_MODEL`
  is what makes model comparison cheap; direct SDK migration is a later, deliberate step.
- **Chroma stays local until Phase 6.** Collapsing into pgvector is a production concern;
  doing it earlier would trade measurable local iteration for deployment convenience.

## Learning Goals

This project is the primary vehicle for reaching **AI Engineering Level 4** (multi-agent system designer) within 6 months, covering:

- Tool-calling agents (deep)
- Memory systems — semantic, episodic, reflection (medium)
- RAG & retrieval (medium)
- Multi-agent orchestration with LangGraph (medium)
- MCP server design (medium)
- Evaluation with LLM judges (medium)
- Production deployment (light)

**Intentionally skipped:** fine-tuning, training pipelines, GPU infrastructure.

---

## Guiding Principles

1. **Build to learn, not to ship** — correctness and understanding over polish
2. **Breadth over depth** — cover the AI engineering map, don't rabbit-hole
3. **One evolving product** — add capabilities to Voyager rather than starting fresh
4. **Understand the infrastructure** — know enough about each layer to reason about tradeoffs (like ECS/Lambda)
