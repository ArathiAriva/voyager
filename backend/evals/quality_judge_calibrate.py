"""Pick a quality judge by measured agreement with hand labels (OPEN-ITEMS S-13).

The quality judge defaults to the model being evaluated, so every historical
`mean_score` carries self-preference bias. This replays stored replies through
candidate judges and reports how well each tracks a human's scores, so the default
can be chosen on evidence rather than on the plausible-sounding argument that a
different provider must be more neutral.

**That argument was tested once and was wrong.** The safety-side calibration (S-8)
found the cross-provider judge *worse* — 33% vs 80% agreement — because it anchored
on the lunch slot and ignored dinner. Self-preference bias here is a hypothesis to
measure, not a conclusion to act on.

Three agreement measures, because "agreement" is not obvious for five ordinal
dimensions and the right one depends on the decision:

- **exact** — the judge gives the same 1-5 as the labeller. Strict: 4 vs 5 on
  `actionability` is not a real disagreement, so a low exact rate alone is weak
  evidence.
- **within-1** — off by at most one point. The usual working definition.
- **rank correlation** (Spearman, over per-run mean scores) — does the judge *order*
  plans the way the labeller does? This is the one that matters most for the
  decision S-13 gates: an A/B between planners needs relative ranking, not absolute
  scores. A judge can be systematically harsh and still rank perfectly.

Also reports **bias**: mean(judge) - mean(label), signed. A judge scoring itself is
expected to run positive; measuring that is the point.

Replays stored replies only -- no agent calls. Costs one judge call per labelled
run per candidate model.

Usage (from backend/):
    python -m evals.quality_judge_calibrate --labels evals/quality_labels.json
    python -m evals.quality_judge_calibrate --labels l.json --models a,b
"""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from evals.judge import DIMENSIONS, judge_reply  # noqa: E402
from evals.quality_labels_template import load_runs  # noqa: E402

EVALS_DIR = Path(__file__).parent
RESULTS_DIR = EVALS_DIR / "results"

CANDIDATES = [
    "anthropic/claude-haiku-4-5",
    "anthropic/claude-sonnet-4-5",
    "openai/gpt-4o-mini",
    "google/gemini-2.5-flash-lite",
]


def _spearman(a: list[float], b: list[float]) -> float | None:
    """Rank correlation. None when there is nothing to correlate.

    Written out rather than pulling in scipy: the eval harness has no numeric
    dependencies today and one function does not justify adding them. Ties get
    averaged ranks, which matters here because 1-5 scores tie constantly.
    """
    n = len(a)
    if n < 2:
        return None

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: values[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            average = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = average
            i = j + 1
        return out

    rank_a, rank_b = ranks(a), ranks(b)
    mean_a = sum(rank_a) / n
    mean_b = sum(rank_b) / n
    numerator = sum((x - mean_a) * (y - mean_b) for x, y in zip(rank_a, rank_b))
    denominator = (
        sum((x - mean_a) ** 2 for x in rank_a) ** 0.5
        * sum((y - mean_b) ** 2 for y in rank_b) ** 0.5
    )
    return numerator / denominator if denominator else None


async def _score_one(row: dict, model: str) -> dict | None:
    try:
        result = await judge_reply(
            prompt=row["prompt"] or "",
            reply=row["reply"] or "",
            itinerary=row.get("itinerary"),
            judge_model=model,
        )
        return {d: result["scores"][d]["score"] for d in DIMENSIONS}
    except Exception as exc:  # noqa: BLE001 -- one bad judge must not kill the sweep
        print(f"    error on {row.get('case_id')}: {str(exc)[:70]}")
        return None


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--labels", required=True, help="hand-labelled file from quality_labels_template")
    parser.add_argument("--models", help="comma-separated (default: built-in candidates)")
    parser.add_argument("--run", help="restrict to one results directory")
    parser.add_argument("--all", action="store_true", help="rebuild the row list from every run")
    args = parser.parse_args()

    payload = json.loads(Path(args.labels).read_text())
    labels = payload.get("labels", payload)
    rows = load_runs(args.run, args.all)

    # Only entries with a complete set of hand scores. A partially-scored entry
    # would silently weight some dimensions differently between judges.
    scored: list[tuple[int, dict, dict]] = []
    for key, label in labels.items():
        if not key.isdigit() or int(key) >= len(rows):
            continue
        truth = (label or {}).get("scores") or {}
        if all(isinstance(truth.get(d), (int, float)) for d in DIMENSIONS):
            scored.append((int(key), rows[int(key)], truth))

    if not scored:
        raise SystemExit(
            f"No fully-scored entries in {args.labels}. Fill in every dimension for "
            "at least a few entries — partially-scored ones are skipped so that all "
            "judges are compared on identical data.")

    models = args.models.split(",") if args.models else CANDIDATES
    print(f"{len(scored)} labelled run(s); testing {len(models)} judge(s)")
    if len(scored) < 10:
        print(f"NOTE: {len(scored)} labels is below the 10-15 S-13 asks for. Enough to "
              f"catch a badly-miscalibrated judge, not to rank close ones.")
    print()

    table: dict[str, dict] = {}
    for model in models:
        print(f"  {model} ...", flush=True)
        exact = within1 = compared = 0
        deltas: list[float] = []
        judge_means: list[float] = []
        label_means: list[float] = []
        per_dimension: dict[str, list[float]] = {d: [] for d in DIMENSIONS}
        errors = 0

        for _, row, truth in scored:
            got = await _score_one(row, model)
            if got is None:
                errors += 1
                continue
            for dimension in DIMENSIONS:
                difference = got[dimension] - truth[dimension]
                compared += 1
                exact += difference == 0
                within1 += abs(difference) <= 1
                deltas.append(difference)
                per_dimension[dimension].append(difference)
            judge_means.append(sum(got.values()) / len(DIMENSIONS))
            label_means.append(sum(truth[d] for d in DIMENSIONS) / len(DIMENSIONS))

        table[model] = {
            "labels": len(scored),
            "errors": errors,
            "comparisons": compared,
            "exact_rate": exact / compared if compared else 0.0,
            "within1_rate": within1 / compared if compared else 0.0,
            "bias": sum(deltas) / len(deltas) if deltas else 0.0,
            "rank_correlation": _spearman(judge_means, label_means),
            "per_dimension_bias": {
                d: (sum(v) / len(v) if v else 0.0) for d, v in per_dimension.items()
            },
        }
        stats = table[model]
        correlation = stats["rank_correlation"]
        print(f"    exact {stats['exact_rate']:.0%}  within-1 {stats['within1_rate']:.0%}  "
              f"bias {stats['bias']:+.2f}  rank r "
              f"{'n/a' if correlation is None else f'{correlation:+.2f}'}"
              f"{f'  (errors {errors})' if errors else ''}")

    # Ranked by rank correlation first: ordering plans correctly is what the
    # planner A/B actually needs. Within-1 breaks ties, then least absolute bias.
    def sort_key(model: str) -> tuple:
        stats = table[model]
        return (
            stats["rank_correlation"] if stats["rank_correlation"] is not None else -2,
            stats["within1_rate"],
            -abs(stats["bias"]),
        )

    best = max(table, key=sort_key)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = RESULTS_DIR / f"quality-calibration-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "calibration.json").write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(),
        "labels_file": args.labels,
        "labelled_runs": len(scored),
        "results": table,
        "recommended": best,
    }, indent=2))

    lines = [
        "# Quality judge calibration (OPEN-ITEMS S-13)",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Labelled runs: {len(scored)} × {len(DIMENSIONS)} dimensions",
        "",
        "**Rank correlation is the headline.** A judge can be systematically harsh and",
        "still rank plans correctly, and ranking is what a planner A/B needs. `bias` is",
        "mean(judge) − mean(label): positive means the judge scores higher than the",
        "human, which is what self-preference would look like.",
        "",
        "| Judge | Rank r | Within-1 | Exact | Bias | Errors |",
        "|---|---|---|---|---|---|",
    ]
    for model, stats in sorted(table.items(), key=lambda kv: -sort_key(kv[0])[0]):
        correlation = stats["rank_correlation"]
        lines.append(
            f"| `{model}` | {'n/a' if correlation is None else f'{correlation:+.2f}'} "
            f"| {stats['within1_rate']:.0%} | {stats['exact_rate']:.0%} "
            f"| {stats['bias']:+.2f} | {stats['errors']} |")
    lines += [
        "",
        f"**Recommended:** `{best}`",
        "",
        "Per-dimension bias (which dimensions a judge is softest on):",
        "",
        "| Judge | " + " | ".join(DIMENSIONS) + " |",
        "|---" * (len(DIMENSIONS) + 1) + "|",
    ]
    for model, stats in table.items():
        cells = " | ".join(f"{stats['per_dimension_bias'][d]:+.2f}" for d in DIMENSIONS)
        lines.append(f"| `{model}` | {cells} |")
    lines += [
        "",
        "## Caveats",
        "",
        f"- {len(scored)} labels over five dimensions is a small sample. It separates a",
        "  badly-miscalibrated judge from a reasonable one; it does not support fine",
        "  claims like \"A is 4% better than B\".",
        "- Historical `mean_score` values were produced by a self-judging setup and are",
        "  not comparable to scores from a different judge without re-judging.",
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n")

    print(f"\nrecommended: {best}")
    print(f"written to {out_dir}/report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
