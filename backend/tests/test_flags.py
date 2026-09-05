"""Feature-flag resolution."""

import pytest

from app import flags


# ── Demo-trip seeding ───────────────────────────────────────────────────────

def test_seeding_is_on_by_default(monkeypatch):
    """Unset must keep seeding on, or every existing profile silently changes
    behaviour the next time it boots against an empty database."""
    monkeypatch.delenv("VOYAGER_SEED_DEMO_TRIPS", raising=False)
    assert flags.seed_demo_trips() is True


@pytest.mark.parametrize("value", ["0", "false", "False", "no", "off", " 0 ", "OFF"])
def test_seeding_disabled_by_falsey_values(monkeypatch, value):
    monkeypatch.setenv("VOYAGER_SEED_DEMO_TRIPS", value)
    assert flags.seed_demo_trips() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", ""])
def test_seeding_stays_on_for_other_values(monkeypatch, value):
    """Anything not explicitly falsey leaves seeding on. A typo should fail
    towards the existing behaviour rather than silently emptying a profile."""
    monkeypatch.setenv("VOYAGER_SEED_DEMO_TRIPS", value)
    assert flags.seed_demo_trips() is True


# ── Planner ─────────────────────────────────────────────────────────────────

def test_planner_defaults_to_multi(monkeypatch):
    monkeypatch.delenv("VOYAGER_PLANNER", raising=False)
    assert flags.resolve_planner() == "multi"


def test_planner_request_override_beats_env(monkeypatch):
    monkeypatch.setenv("VOYAGER_PLANNER", "multi")
    assert flags.resolve_planner("single") == "single"


def test_planner_ignores_invalid_values(monkeypatch):
    monkeypatch.delenv("VOYAGER_PLANNER", raising=False)
    assert flags.resolve_planner("nonsense") == "multi"
