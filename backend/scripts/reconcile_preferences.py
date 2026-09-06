"""Reconcile contradictory or duplicate preferences in the semantic collection.

Write-time dedup (M-3) handles re-wordings by embedding distance, and supersedes
the stored row when one arrives -- so a reversal stated close to its opposite is
caught there. This handles what distance cannot: pairs far enough apart to be
stored separately but still in conflict, or saying the same thing in words too
different to measure as duplicates.

Distance genuinely cannot make this call. Measured on real embeddings:

    CONTRADICT  0.303   'prefers 3-day trips'       vs 'prefers week-long trips'
    AGREE       0.688   'does not drink alcohol'    vs 'dislikes alcohol'
    AGREE       1.049   'enjoys street food'        vs 'loves cheap local eats'
    DISTINCT    1.184   'enjoys shopping'           vs 'likes museums'
    CONTRADICT  1.272   'travels on a tight budget' vs 'enjoys luxury hotels'

so a model judges the candidate pairs -- one call for the whole batch.

Dry-run by default. Costs one LLM call either way; only --apply deletes.

Usage (from backend/, with the target profile's env):
    python -m scripts.reconcile_preferences                  # dry run
    python -m scripts.reconcile_preferences --apply          # actually resolve
    python -m scripts.reconcile_preferences --max-pairs 20   # bound the batch
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app import memory  # noqa: E402
from app.reconcile import reconcile_preferences  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="delete the superseded rows (default: dry run)")
    parser.add_argument("--max-pairs", type=int, default=40,
                        help="cap the pairs sent for judgement (default 40)")
    args = parser.parse_args()

    total = memory._semantic().count()
    print(f"{total} preference(s) in the semantic collection\n")
    if total < 2:
        print("nothing to reconcile")
        return 0

    resolutions = await reconcile_preferences(apply=args.apply, max_pairs=args.max_pairs)
    if not resolutions:
        print("no contradictions or duplicates found")
        return 0

    for resolution in resolutions:
        print(f"  {resolution.verdict}  (d={resolution.distance:.3f})")
        print(f"    keep  {resolution.keep_text}")
        print(f"    drop  {resolution.drop_text}")

    if args.apply:
        print(f"\nresolved {len(resolutions)} pair(s); "
              f"{memory._semantic().count()} preference(s) remain")
    else:
        print(f"\nDry run — {len(resolutions)} pair(s) would be resolved. "
              f"Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
