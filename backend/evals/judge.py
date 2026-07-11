"""LLM-as-judge for itinerary quality.

Scores one planning reply on five dimensions (1-5 each). Output schema is
LangSmith-compatible: each dimension maps to {"score": float, "comment": str}
so results can later be uploaded as LangSmith feedback without reshaping.
"""
import json
import logging
import re

from app.claude import get_client, get_model

logger = logging.getLogger("voyager.evals.judge")

DIMENSIONS = [
    "geographic_coherence",
    "personalization",
    "feasibility",
    "completeness",
    "actionability",
]

JUDGE_SYSTEM = """You are an expert travel-planning evaluator. Score the assistant's \
trip plan on each dimension from 1 (poor) to 5 (excellent). The plan may consist of \
a chat reply plus a persisted day-by-day itinerary saved to the user's trip; when an \
itinerary is provided, judge the reply and itinerary together as one deliverable — \
detail in the saved itinerary counts even if the reply only summarizes it. Judge only \
what is actually present — do not reward promised-but-absent detail.

Dimensions:
- geographic_coherence: are each day's items plausibly close together; is the day \
ordering sensible (no pointless zigzagging between areas)?
- personalization: does the plan reflect the user's stated constraints and, where \
referenced, their history/preferences/saved places — vs. a generic tourist plan?
- feasibility: realistic pacing, opening hours/seasonality awareness, transit time, \
special constraints (weather, altitude, budget) honoured?
- completeness: does it cover the full requested duration and all requested themes, \
with concrete places rather than placeholders?
- actionability: could the user follow this tomorrow — specific names, areas, \
rough timing — and does it note what still needs booking/deciding?

Respond with JSON only:
{
  "geographic_coherence": {"score": <1-5>, "comment": "<one sentence>"},
  "personalization": {"score": <1-5>, "comment": "<one sentence>"},
  "feasibility": {"score": <1-5>, "comment": "<one sentence>"},
  "completeness": {"score": <1-5>, "comment": "<one sentence>"},
  "actionability": {"score": <1-5>, "comment": "<one sentence>"},
  "overall_comment": "<two sentences>"
}"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)


def _format_itinerary(itinerary: list[dict]) -> str:
    """Render the persisted ItineraryDay list as readable markdown for the judge."""
    lines = []
    for d in itinerary:
        header = f"Day {d.get('day')}"
        if d.get("date"):
            header += f" ({d['date']})"
        if d.get("title"):
            header += f": {d['title']}"
        lines.append(f"## {header}")
        if d.get("area_focus"):
            lines.append(f"Area focus: {d['area_focus']}")
        if d.get("accommodation"):
            lines.append(f"Accommodation: {d['accommodation']}")
        lines.append(d.get("plan", ""))
        lines.append("")
    return "\n".join(lines).strip()


async def judge_reply(
    prompt: str,
    reply: str,
    itinerary: list[dict] | None = None,
    judge_model: str | None = None,
) -> dict:
    """Return {"scores": {dim: {"score", "comment"}}, "overall_comment": str, "mean_score": float}."""
    from app.usage import usage_context

    usage_context.set("eval_judge")
    client = get_client()
    if itinerary:
        itinerary_block = (
            "\n\nPERSISTED ITINERARY (saved to the user's trip — part of the deliverable):\n"
            + _format_itinerary(itinerary)
        )
    else:
        itinerary_block = "\n\n(No itinerary was persisted to the user's trip for this run.)"
    response = await client.chat.completions.create(
        model=judge_model or get_model(),
        temperature=0.0,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {
                "role": "user",
                "content": f"USER PLANNING REQUEST:\n{prompt}\n\nASSISTANT REPLY:\n{reply}{itinerary_block}",
            },
        ],
    )
    raw = response.choices[0].message.content or ""
    parsed = _extract_json(raw)
    scores = {d: parsed[d] for d in DIMENSIONS}
    mean = sum(s["score"] for s in scores.values()) / len(scores)
    return {
        "scores": scores,
        "overall_comment": parsed.get("overall_comment", ""),
        "mean_score": round(mean, 2),
    }
