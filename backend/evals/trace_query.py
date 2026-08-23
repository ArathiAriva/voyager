"""Read back captured LLM calls from the local trace log.

Companion to app/tracing.py (enable with VOYAGER_TRACE_LLM=1). Mostly exists so
the planner's intermediate outputs -- the build_brief brief above all -- are
inspectable after the fact without writing ad-hoc JSON parsing each time.

Usage (from backend/ dir):

    python -m evals.trace_query                          # last 10 calls, any node
    python -m evals.trace_query --node build_brief       # just the briefs
    python -m evals.trace_query --node build_brief -n 3 --full
    python -m evals.trace_query --nodes                  # what nodes were captured
    python -m evals.trace_query --grep AZURE-PELICAN     # find a string in any field
    python -m evals.trace_query --node critic --json     # raw entries, for piping

Reads VOYAGER_TRACE_PATH (default ./trace_log.jsonl) plus its `.1` rollover.
"""
import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

TRACE_PATH = Path(os.environ.get("VOYAGER_TRACE_PATH", "./trace_log.jsonl"))
PREVIEW_CHARS = 700


def _load(path: Path) -> list[dict]:
    """Read entries oldest-first, including the rolled `.1` file if present."""
    entries: list[dict] = []
    for p in (path.with_suffix(path.suffix + ".1"), path):
        if not p.exists():
            continue
        with p.open() as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"warning: skipping malformed line {p}:{line_no}", file=sys.stderr)
    return entries


def _user_prompt(entry: dict) -> str:
    """The last user-role message -- for build_brief this is the raw context dict."""
    for m in reversed(entry.get("messages") or []):
        if m.get("role") == "user":
            return m.get("content") or ""
    return ""


def _matches_grep(entry: dict, needle: str) -> bool:
    return needle.lower() in json.dumps(entry).lower()


def _print_entry(entry: dict, full: bool) -> None:
    ts = entry.get("ts", "?")
    node = entry.get("node") or "(unset)"
    ctx = entry.get("context", "?")
    model = entry.get("model", "?")
    print(f"\n\033[1m{ts}\033[0m  node={node}  context={ctx}  model={model}")

    output = entry.get("output") or ""
    prompt = _user_prompt(entry)
    if full:
        print("\n--- INPUT (last user message) ---")
        print(prompt)
        print("\n--- OUTPUT ---")
        print(output)
    else:
        if prompt:
            trimmed = prompt[:PREVIEW_CHARS]
            print(f"  in : {trimmed}{'…' if len(prompt) > PREVIEW_CHARS else ''}")
        trimmed_out = output[:PREVIEW_CHARS]
        print(f"  out: {trimmed_out}{'…' if len(output) > PREVIEW_CHARS else ''}")

    if entry.get("tool_calls"):
        names = ", ".join(tc["name"] for tc in entry["tool_calls"])
        print(f"  tools: {names}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--node", help="filter to one graph node (e.g. build_brief, critic)")
    ap.add_argument("--context", help="filter to a usage context (planning, chat, safety_eval, ...)")
    ap.add_argument("--grep", help="only entries containing this string anywhere")
    ap.add_argument("-n", "--last", type=int, default=10, help="how many to show (default 10)")
    ap.add_argument("--full", action="store_true", help="print untruncated input and output")
    ap.add_argument("--json", action="store_true", help="emit raw JSON entries instead of formatted text")
    ap.add_argument("--nodes", action="store_true", help="list captured nodes with counts, then exit")
    ap.add_argument("--path", default=str(TRACE_PATH), help=f"trace file (default {TRACE_PATH})")
    args = ap.parse_args()

    path = Path(args.path)
    entries = _load(path)
    if not entries:
        print(f"No trace entries found at {path}.\n"
              "Is VOYAGER_TRACE_LLM=1 set for the backend process?", file=sys.stderr)
        return 1

    if args.nodes:
        counts = Counter(e.get("node") or "(unset)" for e in entries)
        width = max(len(n) for n in counts)
        print(f"{len(entries)} entries in {path}:\n")
        for node, count in counts.most_common():
            print(f"  {node:<{width}}  {count}")
        return 0

    if args.node:
        entries = [e for e in entries if e.get("node") == args.node]
    if args.context:
        entries = [e for e in entries if e.get("context") == args.context]
    if args.grep:
        entries = [e for e in entries if _matches_grep(e, args.grep)]

    if not entries:
        print("No entries matched those filters.", file=sys.stderr)
        return 1

    selected = entries[-args.last:]

    if args.json:
        for e in selected:
            print(json.dumps(e))
        return 0

    print(f"Showing {len(selected)} of {len(entries)} matching entries from {path}")
    for e in selected:
        _print_entry(e, args.full)
    return 0


if __name__ == "__main__":
    sys.exit(main())
