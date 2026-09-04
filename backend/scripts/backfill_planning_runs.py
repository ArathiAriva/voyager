"""Reconstruct planning runs from `trace_log.jsonl` into planning_run/planning_step.

The trace viewer reads tables that only started being written when the feature
landed, so runs made before that exist only in the JSONL trace log. That log has no
run identifier -- the one real limitation this script works around -- so runs are
recovered by clustering consecutive `context=planning` entries and splitting wherever
the gap between calls exceeds --gap seconds.

Clustering is a heuristic, not a fact: two planning runs issued concurrently would
interleave and be recovered as one. Runs recorded live (post-feature) carry a real id
and are unaffected. Backfilled runs are marked `status="backfilled"` so they are never
mistaken for live captures.

Idempotent: a recovered run whose start timestamp already exists as a backfilled row is
skipped, so re-running (or widening --all after doing one) never duplicates.

Recovered steps carry the node's LLM *response text*, not its state delta -- the trace
log records what each agent said, which is close to but not identical with what the
graph passed on. Summaries are derived from that text where possible.

Usage (from backend/, backend does NOT need to be running):

    python -m scripts.backfill_planning_runs --profile moiraine             # dry run, last run
    python -m scripts.backfill_planning_runs --profile moiraine --apply
    python -m scripts.backfill_planning_runs --profile moiraine --all --apply
"""
import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv


def _load_planning_entries(trace_path: Path) -> list[dict]:
    entries = []
    with trace_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("context") == "planning":
                entries.append(row)
    entries.sort(key=lambda r: r["ts"])
    return entries


#: Every run begins by classifying intent, so a second one marks a new run. This is a
#: far better boundary than a time gap alone: back-to-back planning requests are only
#: seconds apart, and a purely time-based split merged four separate trips (Lisbon,
#: Rome, Valencia, Seville) into one 45-step "run".
_RUN_START_NODE = "classify_intent"


def _cluster(entries: list[dict], gap_seconds: float) -> list[list[dict]]:
    """Split the stream into runs.

    A new run starts at a `classify_intent` call, or wherever the gap between calls
    exceeds `gap_seconds` (which catches runs that failed before classifying).
    """
    runs: list[list[dict]] = []
    current: list[dict] = []
    previous: datetime | None = None
    for row in entries:
        ts = datetime.fromisoformat(row["ts"])
        starts_run = row.get("node") == _RUN_START_NODE
        timed_out = previous is not None and (ts - previous) > timedelta(seconds=gap_seconds)
        if current and (starts_run or timed_out):
            runs.append(current)
            current = []
        current.append(row)
        previous = ts
    if current:
        runs.append(current)
    return runs


def _user_message(cluster: list[dict]) -> str:
    """The originating message, taken from the first node's prompt."""
    for row in cluster:
        messages = row.get("messages")
        if isinstance(messages, str):
            try:
                messages = eval(messages)  # trace log stores a repr
            except Exception:
                continue
        if isinstance(messages, list):
            for m in messages:
                if isinstance(m, dict) and m.get("role") == "user":
                    return str(m.get("content", ""))[:4000]
    return ""


def _parse_output(text: str) -> dict | None:
    """Pull a JSON object out of a node's response, tolerating ``` fences."""
    if not isinstance(text, str):
        return None
    raw = text.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        if len(parts) > 1:
            raw = parts[1]
            if raw.startswith("json"):
                raw = raw[4:]
    try:
        parsed = json.loads(raw.strip())
        return parsed if isinstance(parsed, dict) else {"items": parsed}
    except Exception:
        return None


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", required=True, help="Profile whose DB receives the runs.")
    ap.add_argument("--apply", action="store_true", help="Write. Without this, dry run.")
    ap.add_argument("--all", action="store_true", help="Backfill every recovered run, not just the last.")
    ap.add_argument("--gap", type=float, default=120.0,
                    help="Seconds between calls that starts a new run (default 120).")
    ap.add_argument("--trace", default="trace_log.jsonl", help="Path to the trace log.")
    args = ap.parse_args()

    env_file = BACKEND / "profiles" / f".env.{args.profile}"
    if not env_file.exists():
        print(f"Profile '{args.profile}' not found ({env_file})")
        return 1
    load_dotenv(BACKEND / ".env")
    load_dotenv(env_file, override=True)

    trace_path = Path(args.trace)
    if not trace_path.is_absolute():
        trace_path = BACKEND / trace_path
    if not trace_path.exists():
        print(f"No trace log at {trace_path}")
        return 1

    entries = _load_planning_entries(trace_path)
    if not entries:
        print("No planning entries in the trace log.")
        return 1

    clusters = _cluster(entries, args.gap)
    selected = clusters if args.all else clusters[-1:]

    print(f"trace log:    {trace_path}")
    print(f"profile:      {args.profile} -> {os.environ.get('DATABASE_URL')}")
    print(f"planning calls: {len(entries)}  recovered runs: {len(clusters)}  "
          f"backfilling: {len(selected)}")
    print()

    from app.planning.trace import summarise
    from app.models.orm import PlanningRunORM, PlanningStepORM
    from app.db import SessionLocal
    from sqlalchemy import select

    # Skip anything already recovered, so re-running is safe.
    async with SessionLocal() as session:
        existing = {
            row.created_at
            for row in (await session.execute(
                select(PlanningRunORM).where(PlanningRunORM.status == "backfilled")
            )).scalars().all()
        }

    planned = []
    skipped = 0
    for cluster in selected:
        start = datetime.fromisoformat(cluster[0]["ts"])
        if any(abs((start.replace(tzinfo=None) - e.replace(tzinfo=None)).total_seconds()) < 1
               for e in existing):
            skipped += 1
            continue
        end = datetime.fromisoformat(cluster[-1]["ts"])
        message = _user_message(cluster)
        destination = None
        intent = None
        steps = []
        for i, row in enumerate(cluster):
            node = row.get("node") or "(unknown)"
            parsed = _parse_output(row.get("output", "")) or {}
            if node == "classify_intent":
                intent = parsed.get("intent") or intent
                destination = parsed.get("destination") or destination
            if node == "build_brief":
                destination = parsed.get("destination") or destination
            started = datetime.fromisoformat(row["ts"])
            nxt = datetime.fromisoformat(cluster[i + 1]["ts"]) if i + 1 < len(cluster) else end
            delta = {"brief": parsed} if node in ("classify_intent", "build_brief") else parsed
            steps.append({
                "seq": i,
                "node": node,
                "started_at": started,
                "duration_ms": max(0.0, (nxt - started).total_seconds() * 1000),
                "summary": summarise(node, delta) or (str(row.get("output", ""))[:120]),
                "output": {"response": row.get("output", ""), "parsed": parsed or None},
            })

        planned.append({
            "id": str(uuid.uuid4()),
            "created_at": start,
            "user_message": message,
            "destination": destination,
            "intent": intent,
            "duration_ms": (end - start).total_seconds() * 1000,
            "steps": steps,
        })

        print(f"  run {start:%Y-%m-%d %H:%M}  {destination or '(no destination)'}  "
              f"intent={intent or '?'}  {len(steps)} steps  "
              f"{(end - start).total_seconds():.1f}s")
        print(f"    message: {message[:100]}")
        for s in steps:
            print(f"      {s['seq']}. {s['node']:24} {s['duration_ms']/1000:5.1f}s  {s['summary'][:70]}")
        print()

    if skipped:
        print(f"({skipped} run(s) already backfilled — skipped.)\n")

    if not planned:
        print("Nothing new to backfill.")
        return 0

    if not args.apply:
        print("Dry run — nothing written. Re-run with --apply.")
        return 0

    async with SessionLocal() as session:
        for run in planned:
            session.add(PlanningRunORM(
                id=run["id"],
                created_at=run["created_at"],
                conversation_id=None,
                user_message=run["user_message"],
                destination=run["destination"],
                intent=run["intent"],
                status="backfilled",
                critic_score=None,
                revision_count=0,
                duration_ms=round(run["duration_ms"], 2),
            ))
            for s in run["steps"]:
                session.add(PlanningStepORM(
                    id=str(uuid.uuid4()),
                    run_id=run["id"],
                    seq=s["seq"],
                    node=s["node"],
                    label="",
                    started_at=s["started_at"],
                    duration_ms=round(s["duration_ms"], 2),
                    summary=s["summary"],
                    output=s["output"],
                ))
        await session.commit()

    print(f"Wrote {len(planned)} run(s), marked status=\"backfilled\".")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
