"""Small client for OpenRouter's Jev Decisions API."""

import os
from typing import Any

import httpx


JEV_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_JEV_MODEL = "typesafe/jev-1.13"


def jev_enabled() -> bool:
    return os.environ.get("JEV_ENABLED", "0").lower() in {"1", "true", "yes", "on"}


def memory_filter_enabled() -> bool:
    """Whether Jev should vet extracted preferences before they are retained."""
    return jev_enabled() and os.environ.get("JEV_MEMORY_FILTER_ENABLED", "1").lower() in {
        "1", "true", "yes", "on"
    }


async def classify_planning_intent(message: str) -> tuple[bool, float]:
    """Return whether Jev considers a message planning-related and its confidence."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return False, 0.0

    payload = {
        "model": os.environ.get("JEV_MODEL", DEFAULT_JEV_MODEL),
        "state": {"message": message},
        "questions": {
            "intent": {
                "type": "choice",
                "instructions": "What is the user's primary intent?",
                "criteria": {
                    "planning": "The user wants to plan, revise, or organize a trip itinerary.",
                    "conversation": "The user wants travel information, advice, or casual conversation.",
                    "journal": "The user is recording or reflecting on a travel experience.",
                },
            }
        },
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                JEV_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            answer: dict[str, Any] = response.json()["answers"]["intent"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return False, 0.0

    probabilities = answer.get("probabilities") or {}
    confidence = float(answer.get("confidence", probabilities.get("planning", 0.0)))
    return answer.get("choice") == "planning", confidence


async def filter_durable_preferences(preferences: list[str]) -> list[str]:
    """Keep only high-confidence, durable preferences; fail open on any problem."""
    if not preferences or not memory_filter_enabled():
        return preferences

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return preferences

    questions = {
        f"preference_{index}": {
            "type": "choice",
            "instructions": (
                f"Is `preferences[{index}]` a durable travel preference that should "
                "still influence recommendations for a different trip a year from now?"
            ),
            "criteria": {
                "durable": "A stable, reusable preference about travel style, budget, pace, or tastes.",
                "transient": "A current-trip detail, destination/date-specific fact, or vague observation.",
            },
        }
        for index in range(len(preferences))
    }
    payload = {
        "model": os.environ.get("JEV_MODEL", DEFAULT_JEV_MODEL),
        "state": {"preferences": preferences},
        "questions": questions,
    }

    try:
        threshold = float(os.environ.get("JEV_MEMORY_PREFERENCE_THRESHOLD", "0.80"))
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                JEV_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            answers: dict[str, Any] = response.json()["answers"]

        retained = []
        for index, preference in enumerate(preferences):
            answer: dict[str, Any] = answers[f"preference_{index}"]
            probabilities = answer.get("probabilities") or {}
            confidence = float(answer.get("confidence", probabilities.get("durable", 0.0)))
            if answer.get("choice") == "durable" and confidence >= threshold:
                retained.append(preference)
        return retained
    except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError):
        return preferences
