"""Migration safety tests (INC-001 follow-up).

INC-001 happened because a migration that fails on a *non-empty* SQLite DB
(e.g. ADD COLUMN NOT NULL without a default) was only ever run against empty
databases. These tests walk the full revision chain step by step against a
database that contains data, so any migration that can't handle existing rows
fails here instead of on a real DB.
"""
import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _revisions_base_to_head() -> list[str]:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    return [rev.revision for rev in reversed(list(script.walk_revisions("base", "heads")))]


def _upgrade(db_path: Path, revision: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"}
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        f"alembic upgrade {revision} failed against a non-empty DB "
        f"(INC-001 class of bug):\n{proc.stderr}"
    )


def _seed_if_possible(db_path: Path) -> None:
    """Insert a row into any seedable table that exists at this revision."""
    conn = sqlite3.connect(db_path)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "trips" in tables:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(trips)")}
            base = {"id": str(uuid.uuid4()), "destination": "Testville", "dates": "May 2026",
                    "status": "past", "emoji": "🧪", "summary": "migration fixture"}
            use = {k: v for k, v in base.items() if k in cols}
            conn.execute(
                f"INSERT INTO trips ({','.join(use)}) VALUES ({','.join('?' * len(use))})",
                list(use.values()),
            )
        if "conversations" in tables:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) "
                "VALUES (?, 'migration fixture', '2026-01-01', '2026-01-01')",
                (str(uuid.uuid4()),),
            )
        conn.commit()
    finally:
        conn.close()


def test_migrations_apply_stepwise_to_seeded_db(tmp_path: Path) -> None:
    """Upgrade one revision at a time, seeding data after every step."""
    db_path = tmp_path / "migration_test.db"
    revisions = _revisions_base_to_head()
    assert revisions, "no alembic revisions found"
    for rev in revisions:
        _upgrade(db_path, rev)
        _seed_if_possible(db_path)

    # sanity: seeded data survived the full chain
    conn = sqlite3.connect(db_path)
    try:
        n = conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    finally:
        conn.close()
    assert n >= 1, "seeded rows lost during migration chain"


def test_migrations_apply_to_fresh_db(tmp_path: Path) -> None:
    """Plain base -> head on an empty DB."""
    _upgrade(tmp_path / "fresh.db", "head")
