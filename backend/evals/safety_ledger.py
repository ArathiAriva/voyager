"""Cross-batch ledger of safety-eval results, sliced by model.

Individual runner batches (results/safety-<ts>/) each answer "what happened
that evening". Nothing answered "what do we know across everything we've run,
and which model produced it" -- so Phase 1's headline rate was quoted from a
single 7-run batch while 16 runs sat on disk, and the judge model behind those
numbers had to be recovered from git history.

This aggregates every batch into one table keyed by (case, agent model, judge
model), plus a re-judge history so a judge swap's effect is visible over time.
Read-only over results/; safe to run any time.

Runs predating the model-recording change have no model fields; they are
bucketed as "unrecorded (pre-2026-08-22)" rather than silently merged with
current runs, since combining rates across unknown models is exactly the error
this file exists to prevent.

Usage (from backend/):
    python -m evals.safety_ledger
    python -m evals.safety_ledger --by case      # default
    python -m evals.safety_ledger --by model
"""
import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EVALS_DIR = Path(__file__).parent
RESULTS_DIR = EVALS_DIR / "results"
LEDGER_MD = EVALS_DIR / "SAFETY-LEDGER.md"
UNRECORDED = "unrecorded (pre-2026-08-22)"
# Runs whose reply never reached a research node tested nothing -- they predate
# the runner's full_plan guard. Counting them as passes inflates resistance.
DEGENERATE_REPLY_CHARS = 300


def _wilson(fails: int, n: int) -> tuple[float, float]:
    """95% Wilson score interval for a failure rate. Normal-approximation
    intervals are wrong at these sample sizes (they can dip below 0 and are
    badly off when the rate is 0), and reporting a bare point estimate off
    n=5 is what made Phase 1's rates look more stable than they were."""
    if n == 0:
        return (0.0, 0.0)
    z = 1.96
    p = fails / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - m), min(1.0, c + m))


def _degenerate(r: dict) -> bool:
    return len(r.get("reply") or "") < DEGENERATE_REPLY_CHARS and not r.get("itinerary")


def load_runs() -> list[dict]:
    """Every run from every batch, tagged with its batch and models."""
    out = []
    for d in sorted(RESULTS_DIR.glob("safety-*")):
        f = d / "safety_runs.json"
        if not f.exists():
            continue
        manifest = {}
        mf = d / "manifest.json"
        if mf.exists():
            manifest = json.loads(mf.read_text())
        for r in json.loads(f.read_text()):
            out.append({
                **r,
                "batch": d.name,
                "agent_model": r.get("agent_model") or manifest.get("agent_model") or UNRECORDED,
                "judge_model": r.get("judge_model") or manifest.get("judge_model"),
                "planner": r.get("planner") or "multi",
                "judged": bool(r.get("judgement")),
                "degenerate": _degenerate(r),
            })
    return out


def load_rejudges() -> list[dict]:
    out = []
    for d in sorted(RESULTS_DIR.glob("rejudge-*")):
        f = d / "rejudge.json"
        if f.exists():
            out.append({"batch": d.name, **json.loads(f.read_text())})
    return out


def _stats(runs: list[dict]) -> dict:
    """Failure rate over scored (pass/fail, non-degenerate) runs."""
    # "no_signal" runs (every substantive check skipped) are excluded, like errors:
    # they tested nothing, and counting them as passes is the vacuous-pass failure
    # mode this ledger exists to make visible.
    scored = [r for r in runs if r["verdict"] in ("pass", "fail") and not r["degenerate"]]
    fails = sum(1 for r in scored if r["verdict"] == "fail")
    lo, hi = _wilson(fails, len(scored))
    return {
        "n": len(scored), "fails": fails,
        "rate": fails / len(scored) if scored else 0.0,
        "ci": (lo, hi),
        "errors": sum(1 for r in runs if r["verdict"] == "error"),
        "no_signal": sum(1 for r in runs if r["verdict"] == "no_signal"),
        "excluded": sum(1 for r in runs if r["degenerate"]),
        "judged": sum(1 for r in runs if r["judged"]),
    }


def _fmt(s: dict) -> str:
    lo, hi = s["ci"]
    extra = []
    if s["errors"]:
        extra.append(f"{s['errors']} err")
    if s["excluded"]:
        extra.append(f"{s['excluded']} excl")
    if s.get("no_signal"):
        extra.append(f"{s['no_signal']} no-signal")
    return (f"| {s['fails']}/{s['n']} | {s['rate']:.0%} | {lo:.0%}–{hi:.0%} | "
            f"{s['judged']} | {', '.join(extra) or '—'} |")


def build_report(runs: list[dict], rejudges: list[dict], by: str) -> str:
    live = {c["id"] for c in json.loads((EVALS_DIR / "safety_set.json").read_text())["cases"]}
    L = ["# Safety Eval Ledger", "",
         f"Generated: {datetime.now(timezone.utc).isoformat()}",
         "",
         "Aggregates **every** batch in `results/`, not one evening's run. Rates are",
         "over non-degenerate pass/fail runs; 95% Wilson intervals. Regenerate with",
         "`python -m evals.safety_ledger`.", "",
         f"Total runs on disk: **{len(runs)}** across **{len({r['batch'] for r in runs})}** batches.", ""]

    hdr = ["| Fails | Rate | 95% CI | Judged | Notes |", "|---|---|---|---|---|"]

    if by == "case":
        L += ["## By case × agent model", ""]
        groups: dict[tuple, list] = defaultdict(list)
        for r in runs:
            groups[(r["case_id"], r["planner"], r["agent_model"])].append(r)
        for cid in sorted({k[0] for k in groups}):
            tag = "" if cid in live else "  _(retired case)_"
            L += [f"### `{cid}`{tag}", ""]
            L += ["| Planner | Agent model | Judge model | Fails | Rate | 95% CI | Judged | Notes |",
                  "|---|---|---|---|---|---|---|---|"]
            for (c, pl, am), rs in sorted(groups.items()):
                if c != cid:
                    continue
                jm = sorted({r["judge_model"] or "—" for r in rs})
                L.append(f"| {pl} | `{am}` | {', '.join(f'`{j}`' for j in jm)} " + _fmt(_stats(rs)))
            L.append("")
    else:
        L += ["## By planner x agent model (all cases pooled)", "",
              "| Planner | Agent model | Fails | Rate | 95% CI | Judged | Notes |",
              "|---|---|---|---|---|---|---|"]
        groups = defaultdict(list)
        for r in runs:
            groups[(r["planner"], r["agent_model"])].append(r)
        for (pl, am), rs in sorted(groups.items()):
            L.append(f"| {pl} | `{am}` " + _fmt(_stats(rs)))
        L.append("")

    L += ["## Judge-model history", "",
          "Which judge produced which numbers, and what changed when it was swapped.", ""]
    if rejudges:
        L += ["| Re-judge batch | New judge | Flips | Notes |", "|---|---|---|---|"]
        for rj in rejudges:
            rows = rj["rows"]
            flips = [x for x in rows if not x["agree"]]
            L.append(f"| {rj['batch']} | `{rj['judge_model']}` | {len(flips)}/{len(rows)} | "
                     f"{sum(1 for x in rows if x.get('degenerate'))} excluded |")
        L.append("")
    else:
        L += ["_No re-judge runs yet._", ""]

    L += ["## Known caveats", "",
          f"- Runs marked `{UNRECORDED}` predate per-run model recording; their agent",
          "  and judge model are known only from git history (Phase 1 judged with the",
          "  agent's own model). They are kept separate rather than pooled.",
          "- Only cases declaring a `judge` block produce judged runs; canary cases are",
          "  checked programmatically, so a low judged-count is by design, not neglect.",
          "- Degenerate runs (clarify dead-ends, no itinerary) are excluded from rates.",
          ""]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--by", choices=["case", "model"], default="case")
    args = ap.parse_args()
    runs, rejudges = load_runs(), load_rejudges()
    report = build_report(runs, rejudges, args.by)
    LEDGER_MD.write_text(report)
    print(report)
    print(f"Written to {LEDGER_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
