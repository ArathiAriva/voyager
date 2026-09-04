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
| **3. Trustworthiness** | Agent safety evals — indirect prompt injection, both architectures | 🔄 Active |
| **4. Observability of retrieval** | Retrieval quality monitoring — the unmeasured RAG layer | Next |
| **5. Memory maturity** | Preference provenance → dedup → reconciliation → evolution | Blocked on M-2 |
| **6. Production** | Deployment, auth, Postgres/pgvector, rate limits, quotas | Deferred |

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
- [ ] Preference evolution — moved to Phase 5, and deliberately unscheduled there: it is blocked on M-2 provenance, not on time

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

#### Phase 4 — retrieval observability (next)

The RAG layer is entirely unmeasured. Both eval suites judge the final reply, so a bad
plan cannot be attributed to bad retrieval versus a bad LLM. Two retrieval bugs surfaced
by accident in one session (B-6: Rome plans retrieving Lisbon restaurants, live for
months; S-7: eval fixtures at 3% retrieval share, invalidating a phase of results). A
single recall metric would have caught both.

Design: [docs/retrieval-quality-spec.md](docs/retrieval-quality-spec.md). Always-on
`retrieval_log` first (no labels, no LLM calls), then a small labelled golden set.

#### Phase 5 — memory maturity (blocked)

Sequenced, and the ordering is forced by dependencies:

1. **M-2 — provenance.** `store_preferences` writes no `created_at`/`source`/`trip_id`.
   Nothing downstream is possible without it. Chroma metadata is schemaless, so no
   migration; M-1 already emptied the collection, so there is nothing to backfill —
   **this is the cheapest it will ever be, and it decays with every row written.**
2. **M-3/M-4 — dedup and contradiction reconciliation.** Unglamorous hygiene, but this is
   where the user-visible win is: planning stops pulling a contradictory blob.
3. **B-2's open half** — revoking preferences derived from an edited journal entry falls
   out nearly free once `source` exists.
4. **Preference evolution** — recency weighting, distinguishing genuine change from noise.

Evolution is deliberately **not** scheduled. It needs 1–3 shipped *and* enough real usage
that contradictions accumulate naturally; built earlier, there is no way to validate it.
Phase 4's distance metrics are the signal for when M-3/M-4 become urgent.

#### Phase 6 — production (deferred)

Unchanged: Vercel + Railway/Fly container + Supabase (Postgres, auth, pgvector, collapsing
SQLite and Chroma into one store). Multi-tenant auth, per-user rate limits and LLM budget
quotas built on the existing usage accounting, secrets management, CI running pytest and
both eval suites as regression gates.

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
