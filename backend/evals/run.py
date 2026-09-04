"""Eval runner: golden planning prompts -> live backend -> LLM judge -> report.

Runs each golden case against the running Voyager backend via the real
/conversations API (so tools, memory, and the planner flag all behave exactly
as in production), for one or both planner modes, judges every reply, and
writes JSON results plus a markdown comparison report.

Both planner architectures are supported and reported side by side, never pooled.
The single-agent loop asks before persisting while the graph auto-saves, so when
nothing was persisted the runner plays the cooperative user and confirms once
(`confirmation_turn_used`) -- otherwise the comparison would penalise a planner
for its UX rather than its plan.

Every result records `agent_model` and `judge_model`; the judge defaults to the
model under evaluation, which the report flags as a self-preference-bias caveat.
Backend `event: error` frames are reported as such rather than as "empty reply".

Usage (backend must be running, from backend/ dir):

    python -m evals.run                     # both planners, full golden set
    python -m evals.run --planner multi     # one planner
    python -m evals.run --cases jp-7d,lisbon-3d
    python -m evals.run --judge-model openai/gpt-4o-mini
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

from evals._harness import (adopt_backend_database, iter_sse_frames,
                            parse_error_frame, profile_name)
from evals.judge import DIMENSIONS, judge_reply
from app.claude import get_model

EVALS_DIR = Path(__file__).parent
DEFAULT_BASE_URL = "http://localhost:8060"


def _parse_sse(text: str) -> tuple[dict | None, list[str]]:
    """Return (done_payload, errors) from the SSE stream.

    `errors` carries any `event: error` frames. Without this, a backend failure
    (bad/exhausted API key, provider outage) yields no `done` event, the reply is
    empty, and the run is recorded as the uninformative "empty reply" -- the real
    cause is discarded. That misdiagnosis cost a debugging detour on the safety
    suite on 2026-08-22, so surface it here instead of inferring it.
    """
    done_data = None
    errors: list[str] = []
    for event, payload in iter_sse_frames(text):
        if event == "done":
            done_data = json.loads(payload)
        elif event == "error":
            errors.append(parse_error_frame(payload))
    return done_data, errors


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


async def run_case(client: httpx.AsyncClient, case: dict, planner: str,
                   judge_model: str | None = None) -> dict:
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
    done, sse_errors = _parse_sse(r.text)
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
        _, confirm_errors = _parse_sse(r2.text)
        sse_errors += confirm_errors
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
        # Recorded per run so a score stays interpretable when models change:
        # without these, "mean_score 4.2" cannot be attributed to a config later.
        # judge_model resolves to the agent's own model unless --judge-model is
        # passed, which is a self-preference-bias risk worth being able to see.
        "agent_model": get_model(),
        "judge_model": judge_model or get_model(),
        # An infrastructure failure is reported as itself, not as "empty reply":
        # the distinction is between "the planner produced nothing" (a real quality
        # result) and "the backend never got to answer" (tells you nothing).
        "error": (f"backend error: {sse_errors[0]}" if sse_errors
                  else (None if reply else "empty reply")),
        "sse_errors": sse_errors or None,
    }
    if reply and not sse_errors:
        try:
            result["judgement"] = await judge_reply(case["prompt"], reply, itinerary=itinerary,
                                                    judge_model=judge_model)
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

    # Which models produced these numbers -- a mean_score is not interpretable
    # without them, especially once per-node model choices start varying.
    any_run = next((r for rs in by_planner.values() for r in rs), {})
    agent_model = any_run.get("agent_model")
    judge_model = any_run.get("judge_model")
    if agent_model:
        lines += [f"Agent model: `{agent_model}`", "", f"Judge model: `{judge_model}`", ""]
        if judge_model == agent_model:
            lines += ["> **Caveat:** the judge is the same model being evaluated, so these",
                      "> scores carry self-preference bias. Pass `--judge-model` to vary it.",
                      "> (Note the safety suite's calibration found a *different*-provider judge",
                      "> was measurably worse there, so 'different is better' is not automatic —",
                      "> it needs measuring for quality scoring too.)", ""]

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
    ap.add_argument("--judge-model",
                     help="model to score replies (default: OPENROUTER_MODEL, i.e. the "
                          "same model being evaluated -- see the self-preference caveat "
                          "in evals/README.md)")
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
        # R-3: log judge costs against the profile the backend is actually running,
        # not whatever root .env happens to name.
        adopted = await adopt_backend_database(client)
        print(f"usage logged to profile: {profile_name(adopted)}", flush=True)

        for planner in planners:
            results = []
            for case in golden:
                print(f"[{planner}] {case['id']} ...", flush=True)
                try:
                    result = await run_case(client, case, planner, args.judge_model)
                except Exception as e:
                    result = {"case_id": case["id"], "planner": planner, "error": str(e),
                              "agent_model": get_model(),
                              "judge_model": args.judge_model or get_model()}
                score = result.get("judgement", {}).get("mean_score")
                print(f"[{planner}] {case['id']} -> score={score} latency={result.get('latency_s')}s"
                      + (f" ERROR: {result['error']}" if result.get("error") else ""), flush=True)
                results.append(result)
            by_planner[planner] = results
            (out_dir / f"{planner}.json").write_text(json.dumps(results, indent=2))

    (out_dir / "manifest.json").write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(),
        "agent_model": get_model(),
        "judge_model": args.judge_model or get_model(),
        "judge_is_agent_model": args.judge_model is None,
        "planners": planners,
        "case_ids": [c["id"] for c in golden],
    }, indent=2))
    _write_report(out_dir, by_planner)
    print(f"\nResults written to {out_dir}")
    for p, rs in by_planner.items():
        print(f"  {p}: {_summarize(rs)}")


if __name__ == "__main__":
    asyncio.run(main())
