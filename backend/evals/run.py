"""Eval runner: golden planning prompts -> live backend -> LLM judge -> report.

Runs each golden case against the running Voyager backend via the real
/conversations API (so tools, memory, and the planner flag all behave exactly
as in production), for one or both planner modes, judges every reply, and
writes JSON results plus a markdown comparison report.

Usage (backend must be running, from backend/ dir):

    python -m evals.run                     # both planners, full golden set
    python -m evals.run --planner multi     # one planner
    python -m evals.run --cases jp-7d,lisbon-3d
    python -m evals.run --base-url http://localhost:8060

Results land in evals/results/<timestamp>/.
"""
import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

from evals.judge import DIMENSIONS, judge_reply

EVALS_DIR = Path(__file__).parent
DEFAULT_BASE_URL = "http://localhost:8060"


def _parse_sse(text: str) -> dict | None:
    """Return the JSON payload of the final `done` event, or None."""
    done_data = None
    event = None
    for line in text.splitlines():
        if line.startswith("event: "):
            event = line[len("event: "):].strip()
        elif line.startswith("data: ") and event == "done":
            done_data = json.loads(line[len("data: "):])
    return done_data


async def _trips_snapshot(client: httpx.AsyncClient) -> dict[str, list | None]:
    """Map trip_id -> itinerary for all trips."""
    trips = (await client.get("/api/trips")).json()
    return {t["id"]: t.get("itinerary") for t in trips}


def _diff_itinerary(before: dict, after: dict) -> tuple[str | None, list | None]:
    """Return (trip_id, itinerary) for the trip whose itinerary was created or
    changed by this run, or (None, None) if nothing was persisted."""
    for trip_id, itinerary in after.items():
        if itinerary and itinerary != before.get(trip_id):
            return trip_id, itinerary
    return None, None


async def run_case(client: httpx.AsyncClient, case: dict, planner: str) -> dict:
    conv = (await client.post("/api/conversations")).json()
    trips_before = await _trips_snapshot(client)
    started = time.monotonic()
    r = await client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": case["prompt"], "planner": planner},
        timeout=600,
    )
    latency = round(time.monotonic() - started, 1)
    r.raise_for_status()
    done = _parse_sse(r.text)
    reply = (done or {}).get("content", "")
    trip_id, itinerary = _diff_itinerary(trips_before, await _trips_snapshot(client))

    # Symmetry: some planners ask for confirmation before persisting (e.g. the
    # single-agent loop's create_trip/set_itinerary UX) while others auto-save.
    # Play the cooperative user: if nothing was persisted, confirm once and re-check.
    confirmed = False
    if reply and not itinerary:
        confirmed = True
        r2 = await client.post(
            f"/api/conversations/{conv['id']}/messages",
            json={"content": "Yes, please save this itinerary to my trip.", "planner": planner},
            timeout=600,
        )
        r2.raise_for_status()
        trip_id, itinerary = _diff_itinerary(trips_before, await _trips_snapshot(client))

    result = {
        "case_id": case["id"],
        "planner": planner,
        "prompt": case["prompt"],
        "tags": case.get("tags", []),
        "reply": reply,
        "latency_s": latency,
        "conversation_id": conv["id"],
        "trip_id": trip_id,
        "itinerary": itinerary,
        "confirmation_turn_used": confirmed,
        "error": None if reply else "empty reply",
    }
    if reply:
        try:
            result["judgement"] = await judge_reply(case["prompt"], reply, itinerary=itinerary)
        except Exception as e:  # judge failure shouldn't sink the run
            result["error"] = f"judge failed: {e}"
    return result


def _summarize(results: list[dict]) -> dict:
    ok = [r for r in results if r.get("judgement")]
    summary: dict = {"n": len(results), "judged": len(ok)}
    if ok:
        summary["mean_score"] = round(statistics.mean(r["judgement"]["mean_score"] for r in ok), 2)
        summary["mean_latency_s"] = round(statistics.mean(r["latency_s"] for r in ok), 1)
        for d in DIMENSIONS:
            summary[d] = round(statistics.mean(r["judgement"]["scores"][d]["score"] for r in ok), 2)
    return summary


def _write_report(out_dir: Path, by_planner: dict[str, list[dict]]) -> None:
    lines = ["# Planner Evaluation Report", "", f"Generated: {datetime.now(timezone.utc).isoformat()}", ""]
    summaries = {p: _summarize(rs) for p, rs in by_planner.items()}

    lines += ["## Summary", "", "| Metric | " + " | ".join(summaries) + " |",
              "|---|" + "---|" * len(summaries)]
    metrics = ["mean_score", "mean_latency_s", *DIMENSIONS, "judged"]
    for m in metrics:
        lines.append(f"| {m} | " + " | ".join(str(summaries[p].get(m, "—")) for p in summaries) + " |")

    lines += ["", "## Per-case mean scores", ""]
    planners = list(by_planner)
    lines += ["| Case | " + " | ".join(planners) + " |", "|---|" + "---|" * len(planners)]
    case_ids = [r["case_id"] for r in next(iter(by_planner.values()))]
    indexed = {p: {r["case_id"]: r for r in rs} for p, rs in by_planner.items()}
    for cid in case_ids:
        row = [str(indexed[p].get(cid, {}).get("judgement", {}).get("mean_score", "err")) for p in planners]
        lines.append(f"| {cid} | " + " | ".join(row) + " |")

    (out_dir / "report.md").write_text("\n".join(lines) + "\n")


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--planner", choices=["single", "multi", "both"], default="both")
    ap.add_argument("--cases", help="comma-separated case ids (default: all)")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = ap.parse_args()

    golden = json.loads((EVALS_DIR / "golden_set.json").read_text())["cases"]
    if args.cases:
        wanted = set(args.cases.split(","))
        golden = [c for c in golden if c["id"] in wanted]
    planners = ["single", "multi"] if args.planner == "both" else [args.planner]

    out_dir = EVALS_DIR / "results" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True)

    by_planner: dict[str, list[dict]] = {}
    async with httpx.AsyncClient(base_url=args.base_url) as client:
        for planner in planners:
            results = []
            for case in golden:
                print(f"[{planner}] {case['id']} ...", flush=True)
                try:
                    result = await run_case(client, case, planner)
                except Exception as e:
                    result = {"case_id": case["id"], "planner": planner, "error": str(e)}
                score = result.get("judgement", {}).get("mean_score")
                print(f"[{planner}] {case['id']} -> score={score} latency={result.get('latency_s')}s"
                      + (f" ERROR: {result['error']}" if result.get("error") else ""), flush=True)
                results.append(result)
            by_planner[planner] = results
            (out_dir / f"{planner}.json").write_text(json.dumps(results, indent=2))

    _write_report(out_dir, by_planner)
    print(f"\nResults written to {out_dir}")
    for p, rs in by_planner.items():
        print(f"  {p}: {_summarize(rs)}")


if __name__ == "__main__":
    asyncio.run(main())
