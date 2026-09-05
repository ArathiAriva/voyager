"""Shared plumbing for the eval harnesses (R-2, R-3).

`run.py` (quality) and `safety_run.py` (safety) had grown their own copies of SSE
parsing, trips snapshots, and manifest writing. They drifted once already: the safety
runner learned to read `event: error` frames a day before the quality runner did, and
in that window a 402 from the provider was reported as an uninformative "empty reply".

What lives here is the part that is genuinely identical. Deliberately *not* merged:
`_parse_sse` (safety also needs the graph's step labels) and `_trips_snapshot` (the two
suites need different shapes) -- forcing those into one signature would make both
callers worse. They are built on `iter_sse_frames` below instead, so the frame-level
parsing that actually drifted is shared even though the projections are not.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator

import httpx

DEFAULT_BASE_URL = "http://localhost:8060"


def iter_sse_frames(text: str) -> Iterator[tuple[str | None, str]]:
    """Yield (event_name, raw_data) for each frame in an SSE response body."""
    event: str | None = None
    for line in text.splitlines():
        if line.startswith("event: "):
            event = line[len("event: "):].strip()
        elif line.startswith("data: "):
            yield event, line[len("data: "):]


def parse_error_frame(payload: str) -> str:
    """Extract a human-readable detail from an `event: error` frame."""
    try:
        return json.loads(payload).get("detail", payload)
    except json.JSONDecodeError:
        return payload


async def adopt_backend_database(client: httpx.AsyncClient) -> str | None:
    """Point this process at the same database the backend under test is using.

    R-3: the harnesses run in their own process and called `load_dotenv()` with no
    argument, so `DATABASE_URL` resolved from root `.env` -- typically a dev profile --
    while the backend ran on whatever `run.sh --profile` selected. Judge calls are
    usage-logged by the *harness* process, so their cost landed in the wrong database:
    verified 2026-08-23, when 10 judge calls for a `safetyeval` run were written to
    `egwene.db`.

    Ask the backend which database it is actually using and adopt it, so "what did this
    run cost" is answerable from one place. Returns the adopted URL, or None if the
    backend did not report one (an older build).
    """
    try:
        health = (await client.get("/health")).json()
    except Exception:
        return None

    database_url = health.get("database_url")
    if not database_url:
        return None

    os.environ["DATABASE_URL"] = database_url

    # app.db resolves DATABASE_URL at import, which has already happened by now, so
    # setting the env var alone changes nothing. Compare against the engine's actual
    # URL rather than the env var -- they can disagree, and it is the engine that
    # decides where usage rows land. Let a failure here raise: silently logging a run's
    # cost to the wrong database is the exact problem this function exists to fix.
    import app.db as db

    if db.DB_PATH != database_url:
        db.reconfigure(database_url)
    return database_url


def profile_name(database_url: str | None) -> str:
    """Best-effort profile label from a DATABASE_URL, for manifests and logs."""
    if not database_url:
        return "unknown"
    return Path(database_url.split("///")[-1]).stem or "unknown"


class ProfileGuardError(RuntimeError):
    """Raised when a suite is about to run against a profile it should not touch."""


# Profiles reserved for manual use. An eval run against one of these is almost
# always operator error -- the wrong backend was left on :8060 -- and the damage is
# silent: the suite spends real LLM budget and writes usage_log/retrieval_log rows
# into a profile whose data someone is relying on. The retrieval log is the sharp
# edge, since Phase 4's golden set is meant to be sampled from real queries and
# synthetic eval traffic biases that distribution.
#
# The safety suite already refuses a populated profile (its empty-profile preflight,
# S-7), but the quality suite wants a seeded one, so a personal profile looks
# perfectly valid to it. Hence a name-based reservation rather than a data check.
RESERVED_PROFILES = frozenset({"moiraine"})


def guard_profile(
    database_url: str | None,
    *,
    expect: str | None = None,
    allow_reserved: bool = False,
) -> None:
    """Refuse to run against a reserved or unexpected profile.

    Called after `adopt_backend_database`, so it sees the database the backend is
    actually using rather than whatever this process resolved from `.env` -- the
    same distinction R-3 was about.

    `expect` pins the run to one profile by name, for when a suite has a documented
    target (the safety suite's `safetyeval`). Raises rather than warning: a warning
    scrolls past and the run keeps spending.
    """
    name = profile_name(database_url)

    if not allow_reserved and name in RESERVED_PROFILES:
        raise ProfileGuardError(
            f"Refusing to run: the backend on this URL is using the '{name}' profile, "
            f"which is reserved for manual testing. An eval run would spend LLM budget "
            f"against it and write usage/retrieval rows into data someone is using.\n"
            f"Start a backend on an eval profile instead, e.g.\n"
            f"    bash scripts/run.sh --profile safetyeval    # safety suite\n"
            f"    bash scripts/run.sh --profile egwene        # quality suite\n"
            f"Override with --allow-reserved-profile if this is deliberate."
        )

    if expect and name != expect:
        raise ProfileGuardError(
            f"Refusing to run: expected the '{expect}' profile but the backend is using "
            f"'{name}'. Start it with:\n"
            f"    bash scripts/run.sh --profile {expect}\n"
            f"Override with --allow-any-profile if this is deliberate."
        )
