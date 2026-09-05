"""Trip temporality — is a trip happening right now, and which day is it.

Design doc: docs/live-trip-mode.md

`trips.status` has an "active" value, but it is decorative (a green badge) and
manually set, so it goes stale: a trip marked active in March is still "active"
in September. Liveness is therefore **computed on read** rather than stored --
no scheduler, no migration, and a trip cannot be wrongly live tomorrow because
nothing was written today.

The date source matters. `trips.dates` is free text and across the dev profiles
holds three classes of value:

    explicit range   "September 18-21, 2025"      -> usable
    month only       "April 2024"                 -> identifies a month, not a window
    unparseable      "3 days (dates not specified)"

Only explicit ranges are usable. But itinerary days already carry ISO dates
written by the planner (`{"day": 1, "date": "2025-09-18", ...}`), which is
machine-readable today with no migration and also says which day maps to which
plan. So the itinerary is preferred over the `dates` string.

Returning None is a first-class outcome: most trips have no usable window, and
they must keep behaving exactly as they do now.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime

logger = logging.getLogger("voyager.live_trip")

# Hyphen, en dash, em dash, or the word "to" between two dates. The real data
# uses en dashes ("September 18-21, 2025" is typed with U+2013), so matching only
# ASCII hyphens silently parses nothing -- which is how this was first written.
_RANGE_SEPARATOR = r"\s*(?:[-–—]+|to)\s*"

_MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"], start=1)
}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})


@dataclass(frozen=True)
class TripWindow:
    """A resolved travel window, plus where the dates came from."""

    start: date
    end: date
    source: str  # "itinerary" | "columns" | "dates_string"

    @property
    def total_days(self) -> int:
        return (self.end - self.start).days + 1

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end

    def day_number(self, day: date) -> int | None:
        """1-based day of the trip, or None if `day` falls outside the window."""
        if not self.contains(day):
            return None
        return (day - self.start).days + 1


def _from_itinerary(itinerary: list | None) -> TripWindow | None:
    """Preferred source: the planner writes ISO dates onto itinerary days."""
    if not itinerary:
        return None
    days: list[date] = []
    for entry in itinerary:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("date")
        if not raw:
            continue
        try:
            days.append(datetime.strptime(str(raw)[:10], "%Y-%m-%d").date())
        except ValueError:
            # A single malformed date should not discard the whole itinerary.
            continue
    if not days:
        return None
    return TripWindow(start=min(days), end=max(days), source="itinerary")


def _from_columns(start_date: str | None, end_date: str | None) -> TripWindow | None:
    """Stage 2 source. The columns do not exist yet; this reads them if present so
    the resolver does not need changing when they are added."""
    if not start_date or not end_date:
        return None
    try:
        start = datetime.strptime(str(start_date)[:10], "%Y-%m-%d").date()
        end = datetime.strptime(str(end_date)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return TripWindow(start=start, end=end, source="columns") if start <= end else None


def _from_dates_string(dates: str | None) -> TripWindow | None:
    """Last resort: parse an explicit range out of the free-text `dates` field.

    Deliberately narrow. It matches only ranges that name specific days, because
    a month-only value like "April 2024" identifies a month rather than a travel
    window -- treating it as one would make a trip "live" for 30 days.
    """
    if not dates:
        return None
    text = dates.strip()

    # "September 18-21, 2025" -- one month, two days.
    match = re.search(
        rf"([A-Za-z]+)\s+(\d{{1,2}}){_RANGE_SEPARATOR}(\d{{1,2}}),?\s*(\d{{4}})",
        text,
    )
    if match:
        month_name, first, last, year = match.groups()
        month = _MONTHS.get(month_name.lower())
        if month:
            try:
                return TripWindow(
                    start=date(int(year), month, int(first)),
                    end=date(int(year), month, int(last)),
                    source="dates_string",
                )
            except ValueError:
                return None

    # "August 29 - September 7, 2026" -- crosses a month boundary.
    match = re.search(
        rf"([A-Za-z]+)\s+(\d{{1,2}}){_RANGE_SEPARATOR}([A-Za-z]+)\s+(\d{{1,2}}),?\s*(\d{{4}})",
        text,
    )
    if match:
        start_month_name, first, end_month_name, last, year = match.groups()
        start_month = _MONTHS.get(start_month_name.lower())
        end_month = _MONTHS.get(end_month_name.lower())
        if start_month and end_month:
            try:
                start = date(int(year), start_month, int(first))
                end = date(int(year), end_month, int(last))
                # A range that runs backwards spans a new year ("Dec 28 - Jan 3, 2026").
                if end < start:
                    end = date(int(year) + 1, end_month, int(last))
                return TripWindow(start=start, end=end, source="dates_string")
            except ValueError:
                return None

    return None


def resolve_trip_window(
    itinerary: list | None = None,
    dates: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> TripWindow | None:
    """Best available travel window for a trip, or None if it has no usable dates.

    Order is itinerary → explicit columns → parsed `dates` string, most reliable
    first. None is normal and means live mode does not engage for this trip.
    """
    return (
        _from_itinerary(itinerary)
        or _from_columns(start_date, end_date)
        or _from_dates_string(dates)
    )


def today() -> date:
    """The current date.

    Server-local, which is correct for a single-user local app and wrong once
    this is deployed for users in other timezones -- see the risks section of the
    design doc. Isolated here so tests can patch one place and so the eventual
    per-user timezone has an obvious home.
    """
    return date.today()
