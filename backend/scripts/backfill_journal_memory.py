"""Backfill episodic memory for journal entries that never produced one (B-1).

Journal entries write two things: a `journals` row for RAG (synchronous) and a
derived `journal-{entry_id}` episode (spawned as a background task). When the
background task is lost -- e.g. garbage-collected before `_spawn_extraction`
kept a strong reference to it -- the entry keeps working for `search_journal`
but never reaches `search_memory`. On the `egwene` profile that left 12 journal
entries with 12 `journals` rows and 0 `journal-` episodes.

This finds entries with no corresponding episode and re-runs extraction for
them. It is idempotent: `store_episode` upserts on `journal-{entry_id}`, so
re-running only rewrites what is already there.

Usage (from backend/, backend does NOT need to be running):

    python -m scripts.backfill_journal_memory --profile egwene            # dry run
    python -m scripts.backfill_journal_memory --profile egwene --apply
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True, help="profile name, e.g. egwene")
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    args = ap.parse_args()

    env = BACKEND / "profiles" / f".env.{args.profile}"
    if not env.exists():
        print(f"No such profile: {env}")
        return 1
    load_dotenv(env, override=True)   # profile first
    load_dotenv(BACKEND / ".env")     # then root, for the API key

    # Imported after the env is loaded so DATABASE_URL/CHROMA_PATH resolve correctly.
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.orm import JournalEntryORM, TripORM
    from app import memory as mem
    from app.routers.journal import _extract_journal_memory

    existing = set(mem._episodic().get()["ids"])
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(JournalEntryORM, TripORM.destination)
            .join(TripORM, TripORM.id == JournalEntryORM.trip_id)
        )).all()

    missing = [(e, dest) for e, dest in rows if f"journal-{e.id}" not in existing]
    print(f"profile={args.profile}  journal entries={len(rows)}  "
          f"already have an episode={len(rows) - len(missing)}  missing={len(missing)}")
    if not missing:
        return 0
    for e, dest in missing:
        print(f"  {e.id[:8]}  {e.date}  {dest}  {e.body[:60]!r}")
    if not args.apply:
        print("\nDry run. Re-run with --apply to extract these.")
        return 0

    print(f"\nExtracting {len(missing)} entr{'y' if len(missing) == 1 else 'ies'}...")
    ok = 0
    for e, dest in missing:
        await _extract_journal_memory(e.id, dest, e.body)
        if f"journal-{e.id}" in set(mem._episodic().get()["ids"]):
            ok += 1
        else:
            print(f"  ! entry={e.id[:8]} still has no episode")
    print(f"done: {ok}/{len(missing)} now have an episode")
    return 0 if ok == len(missing) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
