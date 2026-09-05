# Memory & RAG

All vector storage is [Chroma](https://www.trychroma.com/), local, persisted to `backend/chroma_db/` (per-profile; path overridable via `CHROMA_PATH`). Embeddings are Chroma's built-in `all-MiniLM-L6-v2` (local ONNX, ~80 MB cached at `~/.cache/chroma/`, no API key). Code: `backend/app/memory.py`.

## Collections

| Collection | Contents | Written by | Read by |
|---|---|---|---|
| `episodic` | One-sentence summary per conversation (`id = conversation_id`) **and per journal entry** (`id = journal-{entry_id}`); metadata carries `created_at` and `source` | Post-reply background extraction; journal router on create/body-edit | `search_memory` tool |
| `semantic` | Distilled user preferences ("prefers boutique hotels"); deterministic-hash IDs dedupe identical text; metadata carries `created_at`, `source`, and `destination` when known | Post-reply background extraction, journal extraction | `search_memory` tool, planner context gathering |
| `journals` | Full journal entries, auto-indexed on write, per trip | Journal router on entry create/update | `search_journal` tool |
| `saved_places` | Saved-place embeddings; metadata carries `trip_id`, `destination`, `name`, `category` | Places router / `save_place` tool | `search_places` tool |

## Extraction pipeline

Two sources feed `episodic` + `semantic`, both via background LLM passes (usage context
`memory_extraction`):

- **Conversations** — `_extract_and_store_memory` (`routers/conversations.py`) after each reply.
- **Journal entries** — `_extract_journal_memory` (`routers/journal.py`) on create, and on
  PATCH when the `body` changed. Episodes upsert on `journal-{entry_id}`, so an edit
  replaces rather than duplicates.

**Background tasks must retain a strong reference.** `asyncio.create_task(...)` whose
result nobody keeps can be garbage-collected mid-await — no exception, no log, the write
simply never happens. This was B-1: 12 journal entries produced 12 `journals` rows and 0
`journal-` episodes, with nothing in the logs to explain it. `journal.py` now holds tasks
in a module-global set until completion (`_spawn_extraction`), and `conversations.py`
does the same for both of its extraction call sites (B-4). Conversation extraction also
runs under an `asyncio.Semaphore(4)` — every exchange spawns one and each makes an LLM
call, so it queues rather than stampedes. `scripts/backfill_journal_memory.py` repairs
profiles affected by the original bug.

**Spawn background extraction via the module's `_spawn_extraction` helper, never
`asyncio.create_task` directly.**

**Extraction is durable across restarts.** The LLM call and the Chroma write are
seconds apart, and a process teardown in between used to lose the result silently —
`except Exception` does not catch `CancelledError` (B-14). `conversations.extracted_through`
is a watermark set only after a successful write; `retry_unextracted()` re-extracts
conversations whose newest message is later than their watermark at startup, bounded
to 20. Idempotent, since episodes upsert on `conversation_id` and preferences on a
content hash. Cancellation logs a warning and re-raises rather than vanishing.

**`store_preferences` dedupes at write time.** Each incoming preference is checked
against its nearest existing row; within `VOYAGER_PREFERENCE_DEDUPE_DISTANCE`
(default **0.55 L2**, not cosine) it is skipped and the surviving row's
`created_at`/`source` refreshed instead — a re-demonstrated trait is newer
evidence, and aging it out would break "latest wins" reconciliation.

This exists because extraction re-sends the whole transcript every turn (M-6), so
the model re-derives the same trait and re-words it slightly each time; content-hash
IDs only catch identical text. One 20-message conversation produced 13 preferences
covering ~4 traits, including a contradicting pair at 0.978 cosine. Replaying those
13 through the dedup yields 6. Threshold calibrated on that set (real re-wordings
0.04–0.51, first distinct pair 0.600) and deliberately conservative: a kept
duplicate wastes one retrieval slot, while over-merging silently loses a real
trait. Dedup fails open — a failed similarity query still stores the preference.

It handles re-wordings, **not** semantic conflict: two genuinely different traits
that contradict each other are still both stored (M-4).

## Retrieval

The agent calls `search_memory` proactively when personalisation would help (system prompt instructs it to). The planning graph also pulls preferences and saved places into the research brief before dispatching researchers. Journal RAG is exposed via `search_journal`.

**Every search applies a per-collection distance floor.** Chroma returns exactly
`n_results` rows whenever the collection holds that many, so a search could never
report "nothing relevant" — it padded. A logged planning query ("I plan to be there
between 11am and 6pm") returned five preferences at 1.24–1.53, none a real match,
and the planner passed all five to the critic as stated user intent. `_max_distance`
(`memory.py`) drops hits past the floor and returns fewer instead.

The floor is **per-collection because the collections hold different kinds of text**.
Preferences and episodes are sentences that embed close to a natural-language query;
saved places are short noun phrases ("Roman pasta.") that embed far from a full
question however relevant they are. Measured on live data, "dinner recommendations"
over 13 real saved restaurants bottoms out at 1.57 — one global 1.30 floor would
return nothing, a worse failure than the padding. Defaults: `semantic`/`episodic`
1.30, `journals` 1.45, `saved_places` 1.75 (looser because `destination` already does
the real scoping there). Override globally with `VOYAGER_MAX_RETRIEVAL_DISTANCE` or
per collection with `VOYAGER_MAX_RETRIEVAL_DISTANCE_<COLLECTION>`. **All these numbers
are specific to all-MiniLM-L6-v2 L2 distances — changing the embedding model means
recalibrating them.**

**The planner retrieves preferences by facet, not by raw message.** Preferences are
trait statements, but a planning message is mostly logistics, so embedding one against
the other matches on the wrong axis — the logged query above returned three *timing*
preferences because its text was dominated by time-of-day tokens. `load_user_context`
(`agents/planner.py`) runs the user's message plus the `PREFERENCE_FACETS` probes
(food, accommodation, pace, activities, budget, transport), then merges via
`_merge_preference_hits`: dedupe on Chroma ID, keep each row's best distance, rank
globally, cap at `max_preferences` (8). Costs no API calls — MiniLM embeddings are
local. Episodes stay on the raw message; they share its register, so facets don't help.

**Saved-place retrieval is destination-scoped.** `search_saved_places` takes an optional
`destination` and filters with `utils.dest_matches` ("Rome" ~ "Rome, Italy"). Chroma's
`where` can't express fuzzy matching, so the filter runs post-query and the search
over-fetches 5x to avoid starving results. Without it, planning a Rome trip retrieved the
user's saved Lisbon and Istanbul places (B-6). The three planning researchers inject
`destination` from the brief; the single-agent loop passes it itself, which is why the
tool description instructs the model to. Note `trip_id` is *not* usable as the scope
during research — a fresh plan's trip doesn't exist until persist time.

## UI

The Memories page surfaces episodic and semantic memories (`GET /api/memories`,
`routers/memories.py`). Sections are named for the collections themselves —
**Semantic** and **Episodic**. The episodic heading used to read "Past
conversations", which was wrong for a visible fraction of rows: that collection also
holds one summary per *journal entry*. Measured before the profile was reset,
`moiraine` had 9 of 10 such rows from journal entries and `egwene` 12 of 114 —
the share varies by profile, so the heading was misleading rather than merely
imprecise.

Each card carries a **chat/journal source tag**. `_source_of` prefers the `source`
metadata written since M-2, falling back to the `journal-{entry_id}` ID convention
for older rows that have no metadata.

`GET /api/memories` returns `episode_rows`/`preference_rows` (id, text, source,
created_at) alongside the original plain `episodes`/`preferences` string lists, which
stay for existing callers. The rows exist because bare documents were unaddressable —
the UI could not name a specific memory to delete.

`DELETE /api/memories/{episodic|semantic}/{id}` **forgets one memory.** This is the
first delete path against `semantic`, and it only works because preference IDs are
content hashes: under the old per-process `abs(hash())` scheme no caller could
recompute the ID a previous process wrote, so no stored preference could be addressed
or forgotten. Chroma's `delete` is silent on a missing ID, so `_delete_by_id` checks
existence first and the route 404s rather than reporting a false success. Deleting a
memory does **not** delete the conversation or journal entry it was distilled from,
and a preference the user keeps demonstrating can be re-derived by a later
extraction — a journal episode also returns if its entry is edited, since PATCH
re-runs extraction. There is no undo; the `useConfirm` dialog (B-9) is the only guard.

## Future

Month 6 plans to collapse SQLite + Chroma into Supabase Postgres + pgvector; embeddings would move to a hosted model. Don't build toward that yet.
