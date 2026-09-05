"""Collapse near-duplicate preference rows in the semantic collection.

Why this exists: `store_preferences` now dedupes at write time (M-3), but that
only guards *new* writes. Rows accumulated before the fix -- and any written
while the threshold was mis-set -- are still there. Unlike
`purge_preferences.py`, which empties the collection, this keeps one row per
cluster of re-wordings and drops only the redundant phrasings.

Which row survives: the **oldest** in each cluster, on the reasoning that the
first phrasing is what the write-time dedup would have kept had it been running
(it skips incoming duplicates rather than replacing the stored row). Rows with
no `created_at` predate the metadata and sort first. The survivor's timestamp is
refreshed to the newest in its cluster, so a repeatedly re-demonstrated trait
does not read as stale to later recency-based reconciliation.

This merges *re-wordings*, not semantic conflict: two genuinely different traits
that contradict each other are far apart in embedding space and both survive.

Dry-run by default. Writes a JSON backup of every dropped row before deleting.

Usage (from backend/):
    python -m scripts.compact_preferences                    # dry run
    python -m scripts.compact_preferences --apply            # actually compact
    python -m scripts.compact_preferences --distance 0.45    # stricter threshold
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import memory  # noqa: E402


def _clusters(collection, threshold: float) -> list[list[int]]:
    """Union-find over pairs closer than `threshold`, so a chain of re-wordings
    (A~B, B~C) collapses to one cluster even when A and C are further apart."""
    raw = collection.get(include=["documents", "metadatas"])
    ids, documents = raw["ids"], raw["documents"]
    n = len(ids)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, document in enumerate(documents):
        # Query the collection rather than computing embeddings by hand, so this
        # uses exactly the same distance metric the write path does.
        results = collection.query(query_texts=[document], n_results=min(n, 10))
        for other_id, distance in zip(results["ids"][0], results["distances"][0]):
            if other_id == ids[i] or distance > threshold:
                continue
            parent[find(i)] = find(ids.index(other_id))

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    parser.add_argument("--distance", type=float, default=memory._PREFERENCE_DUPLICATE_DISTANCE,
                        help=f"L2 threshold (default {memory._PREFERENCE_DUPLICATE_DISTANCE})")
    args = parser.parse_args()

    collection = memory._semantic()
    total = collection.count()
    if total == 0:
        print("semantic collection is empty; nothing to compact")
        return 0

    raw = collection.get(include=["documents", "metadatas"])
    ids, documents, metadatas = raw["ids"], raw["documents"], raw["metadatas"]

    def created_at(index: int) -> str:
        return ((metadatas[index] or {}).get("created_at")) or ""

    dropped: list[dict] = []
    survivors: list[tuple[str, str]] = []
    for cluster in _clusters(collection, args.distance):
        cluster.sort(key=created_at)  # oldest first; undated sorts first
        keep, rest = cluster[0], cluster[1:]
        survivors.append((ids[keep], documents[keep]))
        newest = max((created_at(i) for i in cluster), default="")
        if rest and args.apply and newest:
            collection.update(ids=[ids[keep]],
                              metadatas=[{**(metadatas[keep] or {}), "created_at": newest}])
        for index in rest:
            dropped.append({"id": ids[index], "document": documents[index],
                            "metadata": metadatas[index], "merged_into": documents[keep]})

    print(f"{total} preference(s) → {len(survivors)} after compaction "
          f"({len(dropped)} redundant, threshold {args.distance})\n")
    for drop in dropped:
        print(f"  drop  {drop['document'][:66]}")
        print(f"    ↳ merged into  {drop['merged_into'][:60]}")

    if not dropped:
        print("nothing to do")
        return 0

    if not args.apply:
        print("\nDry run. Re-run with --apply to delete.")
        return 0

    backup_dir = Path("data/memory-backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = backup_dir / f"preferences-compacted-{stamp}.json"
    path.write_text(json.dumps(
        {"compacted_at": stamp, "threshold": args.distance,
         "chroma_path": os.environ.get("CHROMA_PATH", "./chroma_db"),
         "dropped": dropped}, indent=2))
    print(f"\nbackup written: {path}")

    collection.delete(ids=[d["id"] for d in dropped])
    print(f"deleted {len(dropped)} row(s); {collection.count()} remain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
