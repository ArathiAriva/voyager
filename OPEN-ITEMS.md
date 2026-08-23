# Open Items

Known bugs, deferred decisions, and follow-up work. One place, so items found
mid-investigation don't get stranded in whichever doc happened to surface them.

**What lives where:**

- **This file** — discovered bugs, technical debt, and decisions that are open *now*.
- [VISION.md](VISION.md) — the phased feature roadmap. Planned work, not discovered work.
- [INCIDENTS.md](INCIDENTS.md) — postmortems for things that already went wrong, with closed follow-ups.
- `docs/*.md` — deep analysis backing individual items here; this file links out rather than restating.

Severity is about consequence if left alone, not effort to fix.

---

## Bugs

### B-1 — Journal entries never produce episodic memories · **confirmed live**

`journal.py:68` writes episodes under `journal-{entry_id}`, but the live profile
has **18 journal entries and 0 `journal-` prefixed episodes**. Journal extraction
is failing silently, or the episodes are being lost. `journal.py:72-73` swallows
every exception into a log line, so a persistent failure is invisible.

Journal RAG (`search_journal`) still works — that reads the `journals` collection,
which is populated. What's missing is the derived episodic memory, so journal
content never reaches `search_memory`.

**Severity:** medium — a whole documented feature (Month 2/3 journal→memory) may
be silently dead. **Next step:** create a journal entry with the backend running
and watch the logs; the `except` block will name the failure.
Source: [docs/memory-quality-analysis.md](docs/memory-quality-analysis.md) §2.8.

### B-2 — Journal PATCH re-embeds but never re-extracts

`journal.py:130` calls `store_journal_entry` on update but not
`_extract_journal_memory`. Preferences derived from the original text survive an
edit — including preferences the user just edited away. Asymmetric with delete
(`journal.py:144`), which removes the journal embedding but has no way to remove
derived preferences (blocked on stable IDs, now fixed for preferences by `e966e9f`).

**Severity:** low-medium — silent staleness, no crash.

### B-3 — `test_content.py` mock target is stale · 5 failing tests

All 5 failures are `AttributeError: module 'app.routers.content' does not have
the attribute '_fetch_og_metadata'`. Pre-existing and unrelated to recent work
(verified by stashing changes and re-running). The function was presumably
renamed without updating the patch target.

**Severity:** low, but it's 5 red tests masking real regressions in that module.

### B-4 — Memory extraction is fire-and-forget with no backpressure

`conversations.py:370` spawns an unawaited `asyncio.create_task` per exchange and
retains no reference — under CPython the task can be garbage-collected mid-flight.
Nothing bounds concurrency. Failures are logged and dropped
(`conversations.py:118-119`).

**Severity:** low now, real under load. Plausibly a contributing cause of B-1.

### B-5 — Journal extraction leaks cost attribution

`conversations.py:86` sets `usage_context.set("memory_extraction")`;
`_extract_journal_memory` (`journal.py:46-73`) sets no usage context, so its cost
is attributed to whatever context was last set.

**Severity:** low — but this project's whole point includes cost accounting.

---

## Memory quality

Full analysis: [docs/memory-quality-analysis.md](docs/memory-quality-analysis.md).
Steps 1–2 of its sequencing shipped in `e966e9f` (stable sha256 preference IDs,
durability test in both extraction prompts, critic scoring against the brief's
filtered list). What remains:

### ~~M-1 — The existing preference rows are polluted~~ · **done** (`6d8144b`)

Purged all 292 rows via `scripts/purge_preferences.py` (dry-run by default,
JSON backup written to `backend/data/memory-backups/`). Also dropped 6 orphaned
journal embeddings, so `journals` is now 12/12 consistent with SQLite.

Verified after: a conversation mentioning "5 days", "Tokyo" and "this November"
stored **zero** of those as preferences — only three durable traits — with the
trip detail routed to the episode summary. Under the old prompt all three would
have been stored (the purged set contained `planning a 7-day trip`, `traveling
in November`).

Purge rather than rebuild because preferences are LLM-distilled and exist only
in Chroma — nothing in SQLite reconstructs them. The collection regrows from use.

### M-2 — `store_preferences` has no metadata · **structural unlock**

No `created_at`, `source`, or `trip_id`; rows are written with no metadata at
all. This is the blocker under M-3, M-4, and per-trip scoping. Chroma metadata
is schemaless so no Alembic migration is needed. Now cheaper than when this was
written: M-1 emptied the collection, so there is nothing to backfill — new rows
can carry metadata from the first write.

Note `journals` and `saved_places` already do this correctly (both carry
`trip_id` and filter on it). Only `semantic` and `episodic` skipped it.

### M-3 — Semantic near-duplicates will re-accumulate

Before the M-1 purge, 129/292 rows were paraphrases of the same few food traits,
collapsing retrieval diversity to 2–3 distinct traits per 5 slots. sha256 dedup
can't touch these — they're distinct strings — so the mechanism that produced
them is unchanged and the cluster will rebuild over time. Options: write-time
embedding dedup (~0.88 cosine), periodic compaction, or a cap with LRU.

### M-4 — Nothing reconciles contradictions or bounds growth

No cap, TTL, aging, compaction, or contradiction handling. Growth is monotonic at
~3 preferences per conversation. Depends on M-2.

### M-5 — Preferences aren't scoped to a trip or destination

`enjoys traditional Portuguese cuisine and fado music` is globally retrievable
when planning Tokyo. Depends on M-2; the filter pattern already exists in
`search_journals` (`memory.py:103`).

### M-6 — Every exchange re-extracts the entire transcript · **not worth fixing yet**

`conversations.py:88-92` re-sends the whole conversation to the extractor on every
exchange, so turn 1 is re-processed on turns 2, 3, 4… Quadratic in conversation
length, and the original analysis flagged it as a contributor to both the
duplicate rate and the usage bill.

**Measured 2026-08-22, and the premise doesn't hold at current scale:**
conversations in this profile are median **2** messages, max **4** — so almost
nothing is re-extracted. Across 104 conversations the redundancy is ~1% of turns
sent. Memory extraction is **2% of total LLM spend** ($0.077 over 96 calls), so
the recoverable waste is a fraction of a cent.

Both obvious fixes cost something real in exchange: extracting only the newest
exchange loses cross-turn inference (a preference stated in turn 1 and confirmed
in turn 5 goes unnoticed), and a windowed transcript is a no-op at these lengths.
Adding a processed-watermark to `messages` would need an Alembic migration.

**Revisit when** conversations routinely exceed ~8 messages, or `memory_extraction`
climbs meaningfully as a share of spend — both checkable from `usage_log`.

### M-7 — Episodic memory has its own duplicate problem

3 duplicate document groups among 97 episodes. Here the ID (`conversation_id`,
`memory.py:41`) *is* stable, so these are genuinely distinct conversations that
produced identical summaries. Lower severity than the preference case.

### M-8 — `/api/memories` returns every row unpaginated

`app/routers/memories.py:14`. Was merely ugly at 292 rows; scales linearly.

---

## Safety evals — Phase 2

Spec: [docs/safety-evals-spec.md](docs/safety-evals-spec.md) ·
Results so far: [docs/safety-evals-writeup.md](docs/safety-evals-writeup.md) ·
Ingress map: [Planner Graph Ingress Map](https://claude.ai/code/artifact/c39f8614-48a2-4373-b0d5-a6e690e1e484)

### S-1 — Phase 2 scope is undecided · **blocking Phase 2**

Broad (spread ~30 cases across all 5 newly-traced surfaces) vs. deep (saturate the
two most severe: `existing_itinerary`→optimizer and `user_preferences`→critic).
Recommendation on file is **deep**, because Phase 1 already demonstrated that
4-run rates move (~25% → ~14%) and spreading thin repeats that mistake.

**Decision needed from you.**

### S-2 — The 1/7 suppression rate predates the judge-model change

Those runs were judged by the same model as the agent. The default is now
`google/gemini-2.5-flash-lite` (different provider), but the existing sample
hasn't been re-judged. Re-run or re-score before treating ~14% as final.

### S-3 — Finding 3 rests on one payload shape

The structured-field laundering case used an obviously malformed injection. Whether
laundering holds against a *plausible-looking* corrupted value is untested and
could go the other way.

### S-4 — Untested attack surfaces from the ingress map

Traced and confirmed reachable, no cases written: `existing_itinerary`→optimizer
(most direct — one `PATCH`, zero laundering hops), `user_preferences`→critic (raw,
under an obey-this instruction), the two-hop extraction→preferences path, Jina
`summary` double-laundering, and the auto-save propagation loop.

### S-5 — Write-up venue undecided

LessWrong vs. personal blog + X thread vs. both. Affects length and format, not
content. Non-blocking.

---

## Deferred by design

Not bugs — decisions already made, recorded so they don't get re-litigated.

- **Unsafe-tool-call attack goal** — dropped from Phase 1 because the multi-agent
  graph has no unconfirmed-write moment to exploit. Retarget at the single-agent
  loop in round 2. See the spec's Pilot Cases section.
- **Sycophancy, goal drift, single-agent path** — named future rounds of the safety
  suite, deliberately out of Phase 1/2 scope.
- **Preference evolution** — VISION.md Month 5; needs real usage data.
- **Postgres/pgvector, auth, deployment** — VISION.md Month 6.
