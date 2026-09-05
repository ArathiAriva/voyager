"""Live Trip Mode — trip temporality and the get_current_trip tool.

Design doc: docs/live-trip-mode.md

The central risk is a false positive: wrongly deciding a trip is underway makes
the agent assume a destination the user is nowhere near. So the negative cases
here matter at least as much as the positive ones.
"""

import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db import Base
from app.live_trip import TripWindow, resolve_trip_window
from app.models.orm import TripORM
from app.tools import execute_tool, find_live_trip


# ── Window resolution ───────────────────────────────────────────────────────

@pytest.mark.parametrize("dates,expected", [
    # Real values from the dev profiles.
    ("September 18–21, 2025", (date(2025, 9, 18), date(2025, 9, 21))),
    ("October 10–14, 2025", (date(2025, 10, 10), date(2025, 10, 14))),
    ("August 29 – September 7, 2026", (date(2026, 8, 29), date(2026, 9, 7))),
    # Separator variants.
    ("October 10-14, 2025", (date(2025, 10, 10), date(2025, 10, 14))),
    ("October 10—14, 2025", (date(2025, 10, 10), date(2025, 10, 14))),
    ("October 10 to 14, 2025", (date(2025, 10, 10), date(2025, 10, 14))),
])
def test_explicit_ranges_parse(dates, expected):
    window = resolve_trip_window(dates=dates)
    assert window is not None, f"failed to parse {dates!r}"
    assert (window.start, window.end) == expected


@pytest.mark.parametrize("dates", [
    # Month-only identifies a month, not a travel window. Treating it as one
    # would make a trip "live" for 30 days.
    "April 2024", "March 2026", "June 2026", "September 2023",
    # Genuinely unparseable, and present in real profiles.
    "3 days (dates not specified)", "2 days (current trip)",
    # A single date is not a range.
    "September 5, 2025",
    None, "",
])
def test_unusable_dates_resolve_to_none(dates):
    assert resolve_trip_window(dates=dates) is None


def test_range_crossing_new_year_rolls_the_year_forward():
    window = resolve_trip_window(dates="December 28 – January 3, 2026")
    assert (window.start, window.end) == (date(2026, 12, 28), date(2027, 1, 3))


def test_itinerary_dates_win_over_the_dates_string():
    """The itinerary is machine-readable and written by the planner; the free-text
    `dates` field may be stale or vaguer."""
    itinerary = [{"day": 1, "date": "2026-03-01"}, {"day": 2, "date": "2026-03-02"}]
    window = resolve_trip_window(itinerary=itinerary, dates="September 18–21, 2025")
    assert window.source == "itinerary"
    assert (window.start, window.end) == (date(2026, 3, 1), date(2026, 3, 2))


def test_itinerary_survives_a_malformed_day():
    """One bad date should not discard the whole itinerary."""
    itinerary = [{"day": 1, "date": "2026-03-01"}, {"day": 2, "date": "not-a-date"},
                 {"day": 3, "date": "2026-03-03"}]
    window = resolve_trip_window(itinerary=itinerary)
    assert (window.start, window.end) == (date(2026, 3, 1), date(2026, 3, 3))


def test_itinerary_without_dates_resolves_nothing():
    assert resolve_trip_window(itinerary=[{"day": 1, "plan": "x"}]) is None


def test_explicit_columns_are_used_when_present():
    """Stage 2 forward-compatibility: the resolver reads start/end columns if the
    schema gains them, so it will not need changing."""
    window = resolve_trip_window(start_date="2026-05-01", end_date="2026-05-04")
    assert window.source == "columns"
    assert window.total_days == 4


def test_columns_reject_a_backwards_range():
    assert resolve_trip_window(start_date="2026-05-04", end_date="2026-05-01") is None


# ── Day arithmetic ──────────────────────────────────────────────────────────

def test_day_number_is_one_based_and_bounded():
    window = TripWindow(date(2026, 9, 4), date(2026, 9, 7), "itinerary")
    assert window.total_days == 4
    assert window.day_number(date(2026, 9, 4)) == 1
    assert window.day_number(date(2026, 9, 7)) == 4
    assert window.day_number(date(2026, 9, 3)) is None
    assert window.day_number(date(2026, 9, 8)) is None


def test_single_day_trip_is_one_day_not_zero():
    window = TripWindow(date(2026, 9, 4), date(2026, 9, 4), "itinerary")
    assert window.total_days == 1
    assert window.day_number(date(2026, 9, 4)) == 1


# ── find_live_trip / get_current_trip ───────────────────────────────────────

def _itinerary(start: date, days: int) -> list[dict]:
    return [
        {"day": i + 1, "date": (start + timedelta(days=i)).isoformat(),
         "title": f"Day {i + 1}", "area_focus": f"Area {i + 1}", "plan": f"Plan {i + 1}"}
        for i in range(days)
    ]


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_trip_in_progress_reports_the_right_day(session):
    start = date.today() - timedelta(days=1)  # started yesterday → today is day 2
    session.add(TripORM(id="t1", destination="Halifax", dates="ignored", status="upcoming",
                        emoji="🌊", itinerary=_itinerary(start, 4)))
    await session.commit()

    live = await find_live_trip(session)
    assert live["day_number"] == 2 and live["total_days"] == 4
    assert live["destination"] == "Halifax"
    assert live["today"]["title"] == "Day 2"
    assert [d["title"] for d in live["remaining_days"]] == ["Day 3", "Day 4"]


@pytest.mark.asyncio
async def test_past_and_undated_trips_are_not_live(session):
    session.add_all([
        TripORM(id="t1", destination="Kyoto", dates="April 2024", status="past", emoji="🏯",
                itinerary=_itinerary(date.today() - timedelta(days=90), 3)),
        TripORM(id="t2", destination="Oaxaca", dates="3 days (dates not specified)",
                status="upcoming", emoji="🌮"),
    ])
    await session.commit()

    assert await find_live_trip(session) is None


@pytest.mark.asyncio
async def test_manual_active_status_alone_does_not_make_a_trip_live(session):
    """status="active" is user-declared intent and goes stale -- a trip marked
    active in March is still active in September. Liveness is derived from dates."""
    session.add(TripORM(id="t1", destination="Kyoto", dates="April 2024", status="active",
                        emoji="🏯"))
    await session.commit()

    assert await find_live_trip(session) is None


@pytest.mark.asyncio
async def test_overlapping_trips_prefer_the_most_recent_start_and_report_the_rest(session):
    today = date.today()
    session.add_all([
        TripORM(id="t1", destination="Lisbon", dates="x", status="upcoming", emoji="🌊",
                itinerary=_itinerary(today - timedelta(days=5), 10)),
        TripORM(id="t2", destination="Porto", dates="x", status="upcoming", emoji="🍷",
                itinerary=_itinerary(today - timedelta(days=1), 3)),
    ])
    await session.commit()

    live = await find_live_trip(session)
    assert live["destination"] == "Porto"
    assert live["other_live_trips"] == ["Lisbon"]


@pytest.mark.asyncio
async def test_boundary_days_are_inclusive(session):
    """First and last day of a trip are both live -- an off-by-one here means the
    agent goes blind on arrival or departure day."""
    for offset, label in ((0, "first"), (-3, "last")):
        start = date.today() - timedelta(days=abs(offset))
        s = TripORM(id=f"t{label}", destination=label, dates="x", status="upcoming",
                    emoji="🌊", itinerary=_itinerary(start, 4))
        session.add(s)
        await session.commit()
        assert await find_live_trip(session) is not None, f"{label} day should be live"
        await session.delete(s)
        await session.commit()


@pytest.mark.asyncio
async def test_tool_returns_live_false_with_guidance_when_no_trip(session):
    session.add(TripORM(id="t1", destination="Kyoto", dates="April 2024", status="past", emoji="🏯"))
    await session.commit()

    result = json.loads(await execute_tool("get_current_trip", {}, session))
    assert result["live"] is False
    assert "not on a trip" in result["message"]


@pytest.mark.asyncio
async def test_tool_returns_the_live_trip(session):
    session.add(TripORM(id="t1", destination="Halifax", dates="x", status="upcoming", emoji="🌊",
                        itinerary=_itinerary(date.today(), 3)))
    await session.commit()

    result = json.loads(await execute_tool("get_current_trip", {}, session))
    assert result["live"] is True
    assert result["day_number"] == 1 and result["trip_id"] == "t1"


# ── System-prompt injection ─────────────────────────────────────────────────

def test_live_prompt_names_the_trip_and_day():
    from app.routers.conversations import _live_trip_prompt

    text = _live_trip_prompt({
        "destination": "Halifax, Nova Scotia", "day_number": 2, "total_days": 4,
        "date": "2026-09-05", "today": {"title": "Kejimkujik Hiking", "area_focus": "Kejimkujik"},
        "other_live_trips": [],
    })

    assert "Halifax, Nova Scotia" in text
    assert "day 2 of 4" in text
    assert "Kejimkujik Hiking" in text
    assert "Do not ask which trip they mean" in text


def test_live_prompt_stays_short():
    """It is prepended to every turn while a trip is live, so it must not bloat the
    prompt. ~35 tokens is the budget; assert on characters as a cheap proxy."""
    from app.routers.conversations import _live_trip_prompt

    text = _live_trip_prompt({
        "destination": "Halifax, Nova Scotia", "day_number": 2, "total_days": 4,
        "date": "2026-09-05", "today": {"title": "Kejimkujik Hiking"}, "other_live_trips": [],
    })
    assert len(text) < 600


def test_live_prompt_surfaces_ambiguity_rather_than_hiding_it():
    from app.routers.conversations import _live_trip_prompt

    text = _live_trip_prompt({
        "destination": "Porto", "day_number": 1, "total_days": 3, "date": "2026-09-05",
        "today": None, "other_live_trips": ["Lisbon"],
    })
    assert "Lisbon" in text and "Ask which one" in text
