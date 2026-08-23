"""Purge the semantic (preferences) Chroma collection.

Why this exists: preference rows were written with a per-process-salted ID
(`str(abs(hash(pref)))`), so upsert dedup never survived a restart, and both
extraction prompts invited transient facts ("planning a 7-day trip") to be
stored as durable traits. Both causes are fixed, but the historical rows are
still polluted and still surface in retrieval -- see OPEN-ITEMS.md M-1.

Preferences are distilled by an LLM and stored *only* in Chroma; nothing in
SQLite can reconstruct them. This is a destructive purge, not a rebuild: the
collection regrows naturally from subsequent conversations, now under the
fixed prompt. Genuinely-good preferences are lost until restated.

Dry-run by default. Writes a JSON backup of every purged row before deleting.

Usage (from backend/):
    python -m scripts.purge_preferences                 # dry run, shows what would go
    python -m scripts.purge_preferences --apply         # actually purge
    python -m scripts.purge_preferences --apply --also-reconcile
                                                        # + drop orphaned journal/place
                                                        #   embeddings with no SQLite row
"""
import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app import memory  # noqa: E402  (must follow load_dotenv: CHROMA_PATH is read at import)

BACKUP_DIR = Path("data/memory-backups")

# Rough classifier, for the dry-run report only -- nothing branches on it.
# Mirrors the categories measured in docs/memory-quality-analysis.md so the
# operator can see the composition of what they are about to delete.
TRANSIENT_PAT = re.compile(
    r"\b(planning|currently in|visiting|traveling to|travelling to|"
    r"has visited|visited|wants to visit|expects)\b",
    re.I,
)
FOOD_PAT = re.compile(r"food|dining|cuisine|restaurant|culinary|eat|tapas|market", re.I)


def _db_path() -> Path | None:
    """Resolve the SQLite file from DATABASE_URL, if it points at one."""
    import os

    url = os.environ.get("DATABASE_URL", "")
    if "sqlite" not in url:
        return None
    return Path(url.split("///")[-1])


def _backup(rows: dict, label: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = BACKUP_DIR / f"{label}-{stamp}.json"
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    return path


def _report_semantic(docs: list[str]) -> None:
    transient = [d for d in docs if TRANSIENT_PAT.search(d)]
    food = [d for d in docs if FOOD_PAT.search(d)]
    print(f"  {len(docs)} preference rows")
    print(f"    ~{len(transient)} transient (trip-bound facts stored as durable traits)")
    print(f"    ~{len(food)} food/dining-related "
          f"({len(food) * 100 // len(docs) if docs else 0}% -- the near-duplicate cluster)")
    print("\n  sample of what will be deleted:")
    for d in docs[:8]:
        print(f"    - {d}")
    if len(docs) > 8:
        print(f"    … and {len(docs) - 8} more (full contents go to the backup file)")


def _orphans(collection, live_ids: set[str]) -> list[str]:
    """Embedded IDs with no corresponding row in SQLite."""
    return sorted(set(collection.get()["ids"]) - live_ids)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="actually delete; without this, only reports what would change")
    ap.add_argument("--also-reconcile", action="store_true",
                    help="additionally drop journal/saved-place embeddings whose SQLite row is gone")
    args = ap.parse_args()

    semantic = memory._semantic()
    docs = semantic.get()["documents"] or []
    ids = semantic.get()["ids"]

    print(f"Chroma path: {memory._CHROMA_PATH}")
    print(f"\nsemantic (preferences) — to be purged:")
    if not docs:
        print("  empty, nothing to purge")
    else:
        _report_semantic(docs)

    reconcile_targets: dict[str, list[str]] = {}
    if args.also_reconcile:
        db_file = _db_path()
        if db_file is None or not db_file.exists():
            print(f"\nreconcile: skipped — no SQLite file resolved from DATABASE_URL", file=sys.stderr)
        else:
            db = sqlite3.connect(db_file)
            for name, coll, table in [
                ("journals", memory._journals(), "journal_entries"),
                ("saved_places", memory._places(), "saved_places"),
            ]:
                live = {r[0] for r in db.execute(f"select id from {table}")}
                orphans = _orphans(coll, live)
                reconcile_targets[name] = orphans
                print(f"\n{name} — orphaned embeddings (no row in {table}): {len(orphans)}")
            db.close()

    if not args.apply:
        print("\nDRY RUN — nothing deleted. Re-run with --apply to proceed.")
        return 0

    if docs:
        backup = _backup({"ids": ids, "documents": docs}, "semantic")
        print(f"\nBacked up {len(docs)} preference rows -> {backup}")
        semantic.delete(ids=ids)
        print(f"Deleted {len(ids)} rows from semantic.")

    for name, orphans in reconcile_targets.items():
        if not orphans:
            continue
        coll = memory._journals() if name == "journals" else memory._places()
        rows = coll.get(ids=orphans)
        backup = _backup({"ids": rows["ids"], "documents": rows["documents"]}, f"{name}-orphans")
        print(f"Backed up {len(orphans)} orphaned {name} embeddings -> {backup}")
        coll.delete(ids=orphans)
        print(f"Deleted {len(orphans)} orphaned rows from {name}.")

    print("\nDone. The semantic collection will regrow from subsequent conversations "
          "under the fixed extraction prompt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
