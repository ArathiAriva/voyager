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

### M-1 — The existing 289 preference rows are still polluted

The prompt fix stops new inflow; it doesn't touch history. ~33 transient entries
and 5 contradictory duration claims remain, and were still reaching the critic on
a post-fix verification run. Analysis recommends **rebuilding** the dev collection
over backfilling, given it's a dev profile with known-bad composition.

**Blocks:** honest evaluation of whether the prompt fix worked, since retrieval
still surfaces old rows.

### M-2 — `store_preferences` has no metadata · **structural unlock**

No `created_at`, `source`, or `trip_id`. All 289 live rows have `metadatas = None`.
This is the blocker under M-3, M-4, and per-trip scoping. Chroma metadata is
schemaless so no Alembic migration is needed — but existing rows can't be
backfilled with real timestamps, which is why M-1 leans rebuild.

Note `journals` and `saved_places` already do this correctly (18/18 and 27/27 rows
carry `trip_id` and filter on it). Only `semantic` and `episodic` skipped it.

**Decision needed from you:** rebuild vs. backfill.

### M-3 — 129/289 preferences are semantic near-duplicates

Paraphrases of the same few food traits. sha256 dedup can't touch these — they're
distinct strings. Measured effect: retrieval diversity collapses to 2–3 distinct
traits per 5 slots on food queries. Options are write-time embedding dedup
(~0.88 cosine), periodic compaction, or a cap with LRU.

### M-4 — Nothing reconciles contradictions or bounds growth

No cap, TTL, aging, compaction, or contradiction handling. Growth is monotonic at
~3 preferences per conversation. Depends on M-2.

### M-5 — Preferences aren't scoped to a trip or destination

`enjoys traditional Portuguese cuisine and fado music` is globally retrievable
when planning Tokyo. Depends on M-2; the filter pattern already exists in
`search_journals` (`memory.py:103`).

### M-6 — Every exchange re-extracts the entire transcript

`conversations.py:88-92` re-sends the whole conversation each time. A 20-message
conversation re-extracts the same early preferences ~10 times — a direct
contributor to both the duplicate rate and the usage bill.

### M-7 — Episodic memory has its own duplicate problem

3 duplicate document groups among 97 episodes. Here the ID (`conversation_id`,
`memory.py:41`) *is* stable, so these are genuinely distinct conversations that
produced identical summaries. Lower severity than the preference case.

### M-8 — `/api/memories` returns every row unpaginated

`app/routers/memories.py:14`. Merely ugly at 289 rows; scales linearly.

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
