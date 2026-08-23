"""
Critic Agent — scores the optimized itinerary draft and flags specific issues.
No tools; reads only from state.
"""

import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.claude import llm_call
from app.planning.state import PlanningState
from app.agents import parse_json_response

logger = logging.getLogger("voyager.agents.critic")

SYSTEM_PROMPT = """You are a travel itinerary critic. You receive a planned itinerary and the
user's preferences/memory, and evaluate the plan before it reaches the user.

Score the plan 1–5 and list specific issues with actionable suggestions.

Check for:
1. Internal consistency — does Day N logistically follow Day N-1?
2. Preference alignment — does the plan match the user's stated preferences from memory?
3. Coverage — are high-priority saved places incorporated?
4. Pacing — is there breathing room, or is every hour scheduled?
5. Geography — are meals and activities co-located within each day?

Be SPECIFIC in issues: "Day 4 lunch is in Ginza but morning activities are in Asakusa (40 min apart)"
not "improve geography". Don't rewrite the plan — just score and annotate.

Return JSON only — no prose, no code fences:
{
  "score": 4,
  "issues": [
    {
      "day": 3,
      "severity": "minor | major",
      "description": "Specific issue description",
      "suggestion": "Specific fix suggestion"
    }
  ],
  "overall_notes": "1-2 sentence summary of plan quality"
}

Scoring guide:
5 — Excellent, no significant issues
4 — Good, minor issues only (default target — score here unless there are real problems)
3 — Has specific fixable problems worth one revision
2 — Multiple serious problems
1 — Fundamentally flawed

IMPORTANT: If the user has no saved places, do NOT penalise the plan for using generic
recommendations — that is expected. Only score below 4 if there are genuine structural
problems (bad geography, terrible pacing, preference mismatches, logical inconsistencies).
Be a constructive critic, not a perfectionist."""


async def run(state: PlanningState, session: AsyncSession, model: str | None = None) -> dict:
    brief = state.get("brief", {})
    payload = {
        "itinerary": state.get("itinerary_draft", []),
        # Score against the same preferences the plan was built from, not the
        # raw memory list. build_brief already filters retrieved preferences
        # (dropping stale/contradictory entries); passing the unfiltered list
        # here meant the critic judged the plan against a *different* set than
        # the researchers used -- an unfair evaluation that turned memory noise
        # into wasted revision loops via should_revise. Falls back to the raw
        # list only if the brief has no preferences (e.g. build_brief failed).
        "user_preferences": (
            brief.get("user_context", {}).get("preferences")
            or state.get("user_preferences", [])
        ),
        "brief": brief,
        "unplaced_items": state.get("unplaced_items", []),
        "conflicts": state.get("conflicts", []),
    }

    response = await llm_call(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ],
        model=model,
    )
    try:
        result = parse_json_response(response.choices[0].message.content or "")
        score = result.get("score", 3)
        issues = result.get("issues", [])
        logger.info("critic | score=%d issues=%d", score, len(issues))
        return {
            "critique_score": score,
            "critique_issues": issues,
        }
    except (ValueError, TypeError):
        logger.warning("critic | failed to parse output: %s", (response.choices[0].message.content or "")[:200])
        return {"critique_score": 3, "critique_issues": []}
