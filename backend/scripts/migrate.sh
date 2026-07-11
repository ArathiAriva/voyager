#!/usr/bin/env bash
# Safe migration runner (INC-001 follow-up).
#
# Backs up the SQLite DB before running `alembic upgrade`, and restores it
# automatically if the migration fails — preventing the partially-migrated
# state that caused INC-001.
#
# Usage (from backend/):
#   bash scripts/migrate.sh            # upgrade head
#   bash scripts/migrate.sh <rev>      # upgrade to a specific revision
set -euo pipefail
cd "$(dirname "$0")/.."

TARGET="${1:-head}"
DB_FILE="${VOYAGER_DB_FILE:-voyager.db}"

if [ -f "$DB_FILE" ]; then
  BACKUP="${DB_FILE}.bak.$(date +%Y%m%d-%H%M%S)"
  cp "$DB_FILE" "$BACKUP"
  echo "Backed up $DB_FILE -> $BACKUP"
else
  BACKUP=""
  echo "No existing $DB_FILE — fresh database, nothing to back up."
fi

if alembic upgrade "$TARGET"; then
  echo "Migration to '$TARGET' succeeded."
  if [ -n "$BACKUP" ]; then
    echo "Backup kept at $BACKUP (delete once you've verified the app)."
  fi
else
  status=$?
  if [ -n "$BACKUP" ]; then
    cp "$BACKUP" "$DB_FILE"
    echo "MIGRATION FAILED — restored $DB_FILE from $BACKUP" >&2
  else
    echo "MIGRATION FAILED on fresh database — removing partial $DB_FILE" >&2
    rm -f "$DB_FILE"
  fi
  exit "$status"
fi
