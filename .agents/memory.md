# Memory & RAG

All vector storage is [Chroma](https://www.trychroma.com/), local, persisted to `backend/chroma_db/` (per-profile; path overridable via `CHROMA_PATH`). Embeddings are Chroma's built-in `all-MiniLM-L6-v2` (local ONNX, ~80 MB cached at `~/.cache/chroma/`, no API key). Code: `backend/app/memory.py`.

## Collections

| Collection | Contents | Written by | Read by |
|---|---|---|---|
| `episodic` | One-sentence summary per conversation (id = conversation_id) | Post-reply background extraction | `search_memory` tool |
| `semantic` | Distilled user preferences ("prefers boutique hotels"); deterministic-hash IDs dedupe identical text | Post-reply background extraction | `search_memory` tool, planner context gathering |
| `journals` | Full journal entries, auto-indexed on write, per trip | Journal router on entry create | `search_journal` tool |
| (places) | Saved-place embeddings for semantic search | Places router / `save_place` tool | `search_places` tool |

## Extraction pipeline

After each chat reply, `_extract_and_store_memory` in `routers/conversations.py` runs as a background task: an LLM pass (usage context `memory_extraction`) summarizes the conversation into an episode and extracts any new preferences, then upserts both into Chroma via `store_episode` / `store_preferences`.

## Retrieval

The agent calls `search_memory` proactively when personalisation would help (system prompt instructs it to). The planning graph also pulls preferences and saved places into the research brief before dispatching researchers. Journal RAG is exposed via `search_journal`.

## UI

The Memories page surfaces episodic and semantic memories (`GET /api/memories`, `routers/memories.py`).

## Future

Month 6 plans to collapse SQLite + Chroma into Supabase Postgres + pgvector; embeddings would move to a hosted model. Don't build toward that yet.
