# Data model

## SQLite (per-profile, async SQLAlchemy)

ORM in `backend/app/models/orm.py`; Pydantic schemas in `models/trip.py` and `models/conversation.py`.

| Table | Key columns | Notes |
|---|---|---|
| `trips` | destination, dates, status (`past`/`upcoming`/active), emoji, summary, tags (JSON), `itinerary` (JSON) | Itinerary is a JSON list of `ItineraryDay` (day, date, title, plan, `area_focus`, `accommodation`) — no separate table |
| `journal_entries` | trip_id FK (cascade), date (YYYY-MM-DD), body, source (`app`/`telegram`/`email`) | Auto-embedded into Chroma on write |
| `connected_content` | trip_id FK, type (`album`/`instagram`/`tiktok`/`blog`/`other`), url, thumbnail_url | |
| `saved_places` | trip_id FK, name, category, `area` (used by geospatial optimizer), summary, enrichment_status, **`visited`/`visited_at`** | Enriched via Jina Reader (summary + OG thumbnail). `visited` is mirrored into Chroma metadata so `search_places` can filter on it |
| `conversations` / `messages` | standard chat history; message role + content, plus **`trip_id`** and **`extracted_through`** on conversations | `trip_id` is nullable *permanently* — unscoped and cross-trip chats are first-class (see [trip-scoped-chats](../docs/trip-scoped-chats.md)). `extracted_through` is a watermark set only after memory extraction successfully writes (B-14) |
| `place_anecdotes` | place_id FK (cascade), body, source (`app`/`chat`), created_at | The user's own words about a place, **verbatim** — a separate table so provenance never mixes with the agent-written `notes`/`summary`, which are an injection channel |
| `usage_log` | model, context, prompt/completion/total tokens, cost_usd | One row per LLM call; created by `create_all` at startup — **no Alembic migration exists for it yet** |

## Migrations

Alembic, in `backend/alembic/versions/`. Run with `bash scripts/migrate.sh` (backs up the DB, auto-restores on failure — see INC-001 in `INCIDENTS.md`). `tests/test_migrations.py` runs every migration against a seeded DB as part of pytest — write the migration, run pytest, then migrate. Note: startup also runs `Base.metadata.create_all`, so dev DBs can have tables that migrations don't create.

**Head is `d3f7b26c410a`** (2026-09-05). Recent chain:
`a1f3c9d24e70` extraction watermark → `b7e2a4c81f35` conversations.trip_id →
`c9d4e18a52b6` saved_places.visited → `d3f7b26c410a` place_anecdotes.

`migrate.sh` reads `VOYAGER_DB_FILE` for the backup and `DATABASE_URL` for the
target, so **both must be set per profile** — migrating every profile is a loop over
the eight of them, not one command.

Two traps this session hit:

- **A profile whose DB was deleted has no alembic stamp.** `create_all` rebuilds the
  tables at startup without stamping, so Alembic then tries to replay every
  migration and fails on "table trips already exists". Fix: `alembic stamp <prior
  head>` before upgrading. `migrate.sh` auto-restored from its backup, which is
  INC-001's safeguard working.
- **SQLite cannot add a foreign key with `ALTER TABLE`.** `b7e2a4c81f35` uses
  `batch_alter_table`, which *rebuilds* the table rather than altering in place.

## Chroma

See [memory.md](memory.md) — collections `episodic` (conversations *and* journal entries, the latter keyed `journal-{entry_id}`), `semantic`, `journals`, `saved_places` (metadata carries `trip_id`, `destination`, `name`, `category`, `visited` — `destination` is what scopes planner retrieval), and **`anecdotes`** (the user's own words, metadata `place_id`/`trip_id`/`destination`/`place_name`). Persisted per profile; path from `CHROMA_PATH`.

**Chroma metadata is schemaless**, which is why `created_at`/`source`/`destination`
on preferences (M-2) and `visited` on places needed no migration — only SQLite
columns do.

**`upsert` MERGES metadata rather than replacing it.** Measured, not assumed: a
write that omits a key leaves the old value in place. That silently un-retired the
wrong row when preference supersession was added, so both write paths
delete-then-upsert when the target ID is retired. Also note **`ondelete` is
decorative throughout** — SQLite does not enforce foreign keys without `PRAGMA
foreign_keys=ON`, which the app does not set, so the `CASCADE`s are SQLAlchemy
relationship cascades and `delete_trip` clears `conversations.trip_id` explicitly.

## Profiles

`scripts/run.sh --profile <name>` selects a per-profile SQLite file and Chroma directory, enabling multi-user development. Seed data can be LLM-generated (`backend/scripts/seed.py`).
