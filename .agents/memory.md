# Memory & RAG

All vector storage is [Chroma](https://www.trychroma.com/), local, persisted to `backend/chroma_db/` (per-profile; path overridable via `CHROMA_PATH`). Embeddings are Chroma's built-in `all-MiniLM-L6-v2` (local ONNX, ~80 MB cached at `~/.cache/chroma/`, no API key). Code: `backend/app/memory.py`.

## Collections

| Collection | Contents | Written by | Read by |
|---|---|---|---|
| `episodic` | One-sentence summary per conversation (`id = conversation_id`) **and per journal entry** (`id = journal-{entry_id}`) | Post-reply background extraction; journal router on create/body-edit | `search_memory` tool |
| `semantic` | Distilled user preferences ("prefers boutique hotels"); deterministic-hash IDs dedupe identical text | Post-reply background extraction, journal extraction | `search_memory` tool, planner context gathering |
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
in a module-global set until completion (`_spawn_extraction`); `conversations.py:370` has
the same pattern still unfixed (B-4). `scripts/backfill_journal_memory.py` repairs
profiles affected by the original bug.

## Retrieval

The agent calls `search_memory` proactively when personalisation would help (system prompt instructs it to). The planning graph also pulls preferences and saved places into the research brief before dispatching researchers. Journal RAG is exposed via `search_journal`.

**Saved-place retrieval is destination-scoped.** `search_saved_places` takes an optional
`destination` and filters with `utils.dest_matches` ("Rome" ~ "Rome, Italy"). Chroma's
`where` can't express fuzzy matching, so the filter runs post-query and the search
over-fetches 5x to avoid starving results. Without it, planning a Rome trip retrieved the
user's saved Lisbon and Istanbul places (B-6). The three planning researchers inject
`destination` from the brief; the single-agent loop passes it itself, which is why the
tool description instructs the model to. Note `trip_id` is *not* usable as the scope
during research — a fresh plan's trip doesn't exist until persist time.

## UI

The Memories page surfaces episodic and semantic memories (`GET /api/memories`, `routers/memories.py`).

## Future

Month 6 plans to collapse SQLite + Chroma into Supabase Postgres + pgvector; embeddings would move to a hosted model. Don't build toward that yet.
