"""Emit a hand-labelling template from stored quality runs (OPEN-ITEMS S-13).

Calibration needs ground truth, and the only source of that is a human scoring
itineraries. This writes a JSON skeleton with one entry per judged run — prompt,
reply and itinerary inlined so the labeller has everything in one file — leaving
the five dimension scores blank to fill in.

Fill in every `score` (1-5). `why` is optional but worth writing for the ones you
found hard: when a judge disagrees later, that note is what tells you whether the
judge is wrong or the label was.

Deliberately *not* prefilled with the existing judge's scores. Seeing a number
before you decide anchors you to it, and a label anchored to the judge cannot
measure that judge.

Usage (from backend/):
    python -m evals.quality_labels_template                      # newest run
    python -m evals.quality_labels_template --run 20260823-120750
    python -m evals.quality_labels_template --all -o labels.json
"""
import argparse
import json
from pathlib import Path

EVALS_DIR = Path(__file__).parent
RESULTS_DIR = EVALS_DIR / "results"

from evals.judge import DIMENSIONS  # noqa: E402


def _run_dirs() -> list[Path]:
    """Quality run directories, oldest first. Safety runs are a different shape."""
    return sorted(
        d for d in RESULTS_DIR.glob("*")
        if d.is_dir()
        and not d.name.startswith(("safety-", "judge-calibration", "rejudge", "quality-calibration"))
        and any(d.glob("*.json"))
    )


def load_runs(run: str | None, use_all: bool) -> list[dict]:
    """Judged runs that actually produced something to score, in stable order.

    The index into this list is the label key, so the ordering has to be
    deterministic — `quality_judge_calibrate.py` rebuilds it the same way.
    """
    dirs = _run_dirs()
    if run:
        dirs = [d for d in dirs if d.name == run]
        if not dirs:
            raise SystemExit(f"no run directory named {run!r}")
    elif not use_all:
        dirs = dirs[-1:]

    rows: list[dict] = []
    for directory in dirs:
        for path in sorted(directory.glob("*.json")):
            if path.name == "manifest.json":
                continue
            try:
                payload = json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, list):
                continue
            for entry in payload:
                if not isinstance(entry, dict) or entry.get("error"):
                    continue
                # A run with no reply tested nothing; one with no itinerary is
                # still scorable (the reply alone can be judged), so it stays.
                if not (entry.get("reply") or "").strip():
                    continue
                rows.append({
                    "batch": directory.name,
                    "case_id": entry.get("case_id"),
                    "planner": entry.get("planner"),
                    "prompt": entry.get("prompt"),
                    "reply": entry.get("reply"),
                    "itinerary": entry.get("itinerary"),
                })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a specific results directory name")
    parser.add_argument("--all", action="store_true", help="every quality run, not just the newest")
    parser.add_argument("-o", "--out", default="evals/quality_labels.json")
    args = parser.parse_args()

    rows = load_runs(args.run, args.all)
    if not rows:
        raise SystemExit(
            "No quality runs found to label. Produce some first:\n"
            "    bash scripts/run.sh --profile egwene   # in another shell\n"
            "    python -m evals.run --planner both")

    out_path = Path(args.out)
    if out_path.exists():
        raise SystemExit(f"{out_path} already exists — move it aside rather than "
                         "overwriting hand-written labels")

    template = {
        "_README": [
            "Hand-score each entry 1-5 on every dimension. This is the ground truth "
            "the judge is measured against, so score what you actually think, not "
            "what you expect a model to say.",
            "1 = poor, 3 = acceptable, 5 = excellent. Leave `why` blank unless the "
            "call was hard — those notes are what disambiguate a judge disagreement "
            "from a bad label.",
            "Entries you do not score are skipped, so labelling a subset is fine. "
            "10-15 is enough to tell a badly-miscalibrated judge from a reasonable "
            "one; it is not enough to rank two reasonable judges finely.",
            "Keys are positional. Do not reorder or delete entries — "
            "quality_judge_calibrate.py rebuilds this list in the same order.",
        ],
        "_dimensions": list(DIMENSIONS),
        "labels": {},
    }

    for index, row in enumerate(rows):
        template["labels"][str(index)] = {
            "case_id": row["case_id"],
            "planner": row["planner"],
            "batch": row["batch"],
            "prompt": row["prompt"],
            "reply": row["reply"],
            "itinerary_days": len(row["itinerary"] or []),
            "itinerary": row["itinerary"],
            "scores": {dimension: None for dimension in DIMENSIONS},
            "why": "",
        }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(template, indent=2))
    print(f"wrote {out_path} with {len(rows)} entr{'y' if len(rows) == 1 else 'ies'} to score")
    print(f"dimensions: {', '.join(DIMENSIONS)}")
    if len(rows) < 10:
        print(f"\nNote: only {len(rows)} run(s) available. S-13 wants 10-15 — "
              f"run the quality suite over more cases first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
