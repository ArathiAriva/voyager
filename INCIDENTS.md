# Incident Log

Operational issues encountered during development. Tracked here to inform future decisions around data safety, migrations, and ops practices.

---

## INC-001 — Conversation data loss during migration fix

**Date:** 2026-06-19
**Severity:** Low (dev environment, no real user data)
**Status:** Closed

### What happened

A new Alembic migration (`ce85be5`) added a `tags` column to the `trips` table as `NOT NULL` without a server-side default. SQLite does not support `ALTER TABLE ADD COLUMN NOT NULL` without a default, causing the migration to fail mid-run. The `connected_content` and `journal_entries` tables were created before the failure, leaving the DB in a partially-migrated state.

The fix was to delete `voyager.db` and re-run `alembic upgrade head` from scratch. This wiped all conversations and messages that had been stored in development.

### Root cause

1. SQLite's `ALTER TABLE` limitation — it cannot add a `NOT NULL` column with no server-side default to an existing table with rows.
2. No DB backup before running the migration.
3. Migration not tested against a non-empty DB before applying.

### Impact

All conversation history in the development SQLite DB was lost. No user data affected (dev-only).

### Resolution

- Changed `tags` column to `nullable=True` in both the migration file and the ORM model.
- Deleted and recreated the DB.

### Follow-up actions

- [ ] Add a pre-migration backup step to the dev runbook (e.g. `cp voyager.db voyager.db.bak` before `alembic upgrade head`).
- [ ] Test new migrations against a seeded DB before applying — keep a `seed.sql` or fixture script for this.
- [ ] Consider switching to PostgreSQL before any real user data is stored (PostgreSQL handles `NOT NULL` + `DEFAULT` in `ALTER TABLE` correctly).

---

<!-- Template for new incidents:

## INC-NNN — Short title

**Date:** YYYY-MM-DD
**Severity:** Low | Medium | High
**Status:** Open | Closed

### What happened

### Root cause

### Impact

### Resolution

### Follow-up actions

- [ ] ...

-->
