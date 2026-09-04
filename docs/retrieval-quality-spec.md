# Spec: Retrieval Quality Monitoring

**Status:** Steps 1–3 implemented 2026-09-03; step 4 (labelled golden set) outstanding
**Owner:** Arathi
**Created:** 2026-08-23
**Context:** Voyager is a RAG app whose retrieval layer is entirely unmeasured. This
extends the observability work (Phoenix tracing, `usage_log` cost accounting) with the
missing third pillar — measuring what comes *out* of Chroma before an LLM ever sees it.
Sits in the maintenance/observability phase, not the feature roadmap.

---

## Problem Statement

Four retrieval paths feed the agents, and **nothing measures whether any of them return
the right things**:

| Path | Function | Feeds |
|---|---|---|
| Saved places | `search_saved_places` | `search_places` tool, all three planning researchers |
| Memory | `search_memory` | `search_memory` tool, `build_brief` context |
| Journal | `search_journals` | `search_journal` tool |
| Planner context | `load_user_context` | every planning run |

Both existing eval suites judge the **final reply**. When a plan is bad, they cannot
distinguish "the retriever missed the relevant saved place" from "the LLM ignored it" —
and those need opposite fixes.

This is not hypothetical. Two retrieval failures surfaced in one session (2026-08-22/23),
both silent, both found by accident while reading tool-call logs for unrelated reasons:

- **B-6** — `search_places` was unscoped by destination, so planning a Rome trip retrieved
  the user's saved Lisbon and Istanbul restaurants and could place them in the itinerary.
  Live for months. Measured impact: on a Rome query against the `egwene` profile, 97% of
  retrieved hits were from other destinations.
- **S-7** — safety-eval fixtures were out-competed by real profile data: fixture content
  was 7 of 211 retrieved hits (3%). Most "passes" scored a payload the agent never saw,
  which invalidated an entire phase of results.

A single recall metric would have caught both immediately. Neither had anything to do
with the LLM.

## Goals

1. **Always-on instrumentation.** Record every retrieval call as it happens — the same
   way `usage_log` records every LLM call. This is the primary deliverable; it needs no
   labels and no LLM calls.
2. **Actionable signals without ground truth.** Zero-result rate, distance
   distributions, filter effectiveness, and result saturation are all computable from
   live traffic alone, and each maps to a real failure mode.
3. **A small labelled set for correctness.** Standard IR metrics (recall@k, precision@k,
   MRR) over query/expected-ID pairs, to assert specific behaviours — including
   regressions like B-6.
4. **Cheap enough to run always.** No LLM calls anywhere in this suite. It should run in
   CI on every commit, unlike the ~$4 safety suite.
5. **A measured trigger for memory hygiene.** M-3/M-4 (dedup, contradiction
   reconciliation) currently have no signal saying *when* they are needed. Rising
   retrieval distance on `semantic` is that signal.

## Non-Goals

- **Judging whether retrieved content was *useful*.** A perfectly retrieved preference
  the planner then ignores still scores 1.0 here. That gap belongs to the quality eval.
- **Tuning embeddings or swapping the model.** Measure first; `all-MiniLM-L6-v2` stays.
- **Re-ranking, hybrid search, query rewriting.** Retrieval *improvements* are a separate
  effort that this work exists to justify and evaluate.
- **Replacing Phoenix.** Phoenix traces LLM calls; this covers the vector layer, which
  Phoenix does not see.

---

## Design

### Layer 1 — passive instrumentation (always on)

A `retrieval_log` table, one row per search call, written fail-open exactly like
`usage_log` (an accounting failure must never break a user request).

| Field | Purpose |
|---|---|
| `collection` | `saved_places` / `episodic` / `semantic` / `journals` |
| `query` | the text searched |
| `filters` | `destination` / `trip_id` / `category` actually applied |
| `n_requested`, `n_returned` | zero-result and truncation signals |
| `result_ids` | stable IDs — makes a result auditable after the fact |
| `distances` | similarity scores (Chroma already returns these) |
| `caller` | reuse the existing `usage_context` + `node_context` contextvars, e.g. `planning:food_researcher` |
| `latency_ms` | retrieval is not free at scale |

**What this yields with no labels at all:**

- **Zero-result rate per collection** — the single most actionable number. Rising on
  `saved_places` means scoping is too tight; on `semantic` means memory isn't being found.
- **Distance distribution over time** — if the best hit's distance drifts upward,
  retrieval is degrading. This is the M-3/M-4 trigger.
- **Filter effectiveness** — how often `destination` scoping drops everything. B-6's fix
  could over-correct and nothing would currently say so.
- **Saturation** — `n_returned == n_requested` consistently means the limit is choosing
  for you, not relevance.

### Prerequisite code change

`search_memory` returns **only documents** — no IDs, no distances — so its results are
currently unauditable and unmeasurable. It must return both. `search_saved_places` and
`search_journals` already return IDs and need only distances threaded through. Chroma
returns `ids` and `distances` on every `query()` call; the data exists and is being
discarded.

### Layer 2 — labelled golden set (on demand)

`evals/retrieval_set.json`:

```json
{
  "id": "places-scope-rome",
  "collection": "saved_places",
  "query": "where should I eat",
  "filters": {"destination": "Rome"},
  "expect_ids": ["place-roscioli", "place-pantheon-cafe"],
  "expect_absent_ids": ["place-lisbon-licorista"]
}
```

`expect_absent_ids` is deliberate: it is how B-6 is asserted to stay fixed, and it is the
check the safety suite needed and did not have.

**Metrics.** Recall@k is the headline — a document that is not retrieved cannot be
recovered downstream, whatever the LLM does. Precision@k measures wasted context. MRR
captures ordering, which matters because `n_results` defaults to 5–8 and models weight
early items more heavily.

All are arithmetic. No LLM, no judge, no cost.

### Fixtures

Needs a deterministic corpus: seed known documents, assert on their IDs, tear down. Use
the same empty-profile discipline the safety suite arrived at (`--profile safetyeval`) —
on a populated profile, seeded documents lose to real data and the metrics measure
nothing. That lesson is already paid for; do not re-learn it here.

---

## Build order

1. ~~**`retrieval_log` + instrumentation in `memory.py`**~~ — **done.** All four
   collections (`saved_places`, `episodic`, `semantic`, `journals`), including the
   zero-count early returns, so the zero-result rate is real. Written fail-open from
   `app/retrieval.py`; `saved_places` logs *post-filter* hits, since the destination
   scope is applied after the vector query and is exactly what B-6 got wrong.
2. ~~**Return IDs + distances from `search_memory`**~~ — **done.** Added as
   `episode_hits` / `preference_hits`; the plain lists stay for existing callers, and
   `_execute_search_memory` strips the hits so they don't spend model context.
3. ~~**`GET /api/retrieval/summary`**~~ — **done**, plus `/api/retrieval/recent` for
   eyeballing what a bad number means. The frontend view beside the Usage tab is *not*
   built.
4. **Golden set + `evals/retrieval_run.py`** — the correctness half. Still outstanding.

**Retention decision (open question above):** log everything, no cap — matching
`usage_log`. Revisit with real row counts rather than pre-building a pruning mechanism.

Steps 1–3 deliberately precede 4: live data tells you *which* queries deserve labels, so
you write 20 useful cases instead of 30 guessed ones.

## Success Metrics

**Leading:** every retrieval path logged; zero-rate and distance percentiles visible per
collection; the golden set runs in CI in under a minute with no API cost.

**Lagging (the actual goal):** the next B-6-class retrieval bug is caught by a metric
rather than by someone reading tool-call logs for an unrelated reason.

## Open Questions

- **Retention.** `retrieval_log` grows faster than `usage_log` (several retrievals per
  LLM call). Cap rows, or roll up to daily aggregates past some age?
- **Query text is sensitive.** It contains user message content. `trace_log.jsonl` is
  already unredacted and gitignored; this table lives in the profile DB. Fine for local
  dev, needs a decision before any deployment.
- **Is `load_user_context` a fourth path or a composition of the others?** It calls the
  same primitives; may need no separate instrumentation.

---
*Related: `.agents/evals-ops.md` (tracing, cost accounting), `.agents/memory.md`
(collections, retrieval scoping), `docs/safety-evals-spec.md` (fixture discipline this
inherits), OPEN-ITEMS.md M-2/M-3/M-4 (memory hygiene this would trigger).*
