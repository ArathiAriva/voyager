# Data model

## SQLite (per-profile, async SQLAlchemy)

ORM in `backend/app/models/orm.py`; Pydantic schemas in `models/trip.py` and `models/conversation.py`.

| Table | Key columns | Notes |
|---|---|---|
| `trips` | destination, dates, status (`past`/`upcoming`/active), emoji, summary, tags (JSON), `itinerary` (JSON) | Itinerary is a JSON list of `ItineraryDay` (day, date, title, plan, `area_focus`, `accommodation`) — no separate table |
| `journal_entries` | trip_id FK (cascade), date (YYYY-MM-DD), body, source (`app`/`telegram`/`email`) | Auto-embedded into Chroma on write |
| `connected_content` | trip_id FK, type (`album`/`instagram`/`tiktok`/`blog`/`other`), url, thumbnail_url | |
| `saved_places` | trip_id FK, name, category, `area` (used by geospatial optimizer), summary, enrichment_status | Enriched via Jina Reader (summary + OG thumbnail) |
| `conversations` / `messages` | standard chat history; message role + content | |
| `usage_log` | model, context, prompt/completion/total tokens, cost_usd | One row per LLM call; created by `create_all` at startup — **no Alembic migration exists for it yet** |

## Migrations

Alembic, in `backend/alembic/versions/`. Run with `bash scripts/migrate.sh` (backs up the DB, auto-restores on failure — see INC-001 in `INCIDENTS.md`). `tests/test_migrations.py` runs every migration against a seeded DB as part of pytest — write the migration, run pytest, then migrate. Note: startup also runs `Base.metadata.create_all`, so dev DBs can have tables that migrations don't create.

## Chroma

See [memory.md](memory.md) — collections `episodic`, `semantic`, `journals`, plus place embeddings. Persisted per profile in `backend/chroma_db/`.

## Profiles

`scripts/run.sh --profile <name>` selects a per-profile SQLite file and Chroma directory, enabling multi-user development. Seed data can be LLM-generated (`backend/scripts/seed.py`).
