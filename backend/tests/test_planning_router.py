"""Planning-intent routing.

Routing matters beyond convenience: a revision that misses the router falls
through to the single-agent loop, where `set_itinerary` replaces the whole
itinerary. Under-matching therefore risks losing days, while over-matching sends
ordinary questions through a slow, expensive planning graph.
"""

import pytest

from app.planning.router import is_planning_request


@pytest.mark.parametrize("message", [
    "plan my trip to Halifax",
    "build an itinerary for 3 days in Kyoto",
    "schedule a day trip near Toronto",
])
def test_planning_requests_route_to_the_graph(message):
    assert is_planning_request(message) is True


@pytest.mark.parametrize("message", [
    # Previously matched by the literal phrase list.
    "change day 3 to include the Citadel",
    "update the itinerary to add a brewery",
    # Previously fell through to chat -- the dangerous path.
    "make day 2 more relaxed",
    "actually, can we do the museum on day 2 instead?",
    "add a coffee stop on the second day",
    "swap the afternoon for a hike",
    "drop the museum on the last day",
    "extend day 1 a bit",
])
def test_itinerary_revisions_route_to_the_graph(message):
    assert is_planning_request(message) is True


@pytest.mark.parametrize("message", [
    # A day reference alone is not an edit -- these are questions.
    "what did I do on day 2?",
    "how was the weather in the morning?",
    "what time does the museum open?",
    # No day reference at all.
    "tell me about Halifax",
    "what's the best coffee in town?",
    "did I save any restaurants?",
    "thanks, that looks great",
])
def test_questions_and_chit_chat_stay_on_the_chat_loop(message):
    assert is_planning_request(message) is False


def test_day_reference_alone_does_not_trigger_a_replan():
    """Both halves are required. Matching a day reference on its own would send
    every 'what's on day 2' question through the full planning graph."""
    assert is_planning_request("day 2") is False
    assert is_planning_request("remove the hike") is False  # verb but no day reference
    assert is_planning_request("remove the hike on day 2") is True
