import json
import re
from typing import Any


def scope_search_args(
    args: dict[str, Any],
    brief: dict[str, Any],
    *,
    category: str,
    force_category: bool = False,
) -> dict[str, Any]:
    """Apply the researchers' shared scoping policy to a `search_places` tool call.

    Two rules, previously copy-pasted into food.py, activities.py and
    accommodation.py (R-1):

    - **category** — default the search to the researcher's own domain. Callers that
      pass ``force_category=True`` overwrite whatever the model asked for; the default
      only fills in a missing value.
    - **destination** — scope retrieval to this trip. Researchers have no ``trip_id``
      (a fresh plan's trip is created later, at persist time), so destination is the
      only scope available. Without it a Rome plan also retrieves the user's saved
      Lisbon and Istanbul places -- that was B-6.

    Mutates and returns `args`, so it can be used inline in the tool loop.
    """
    if force_category:
        args["category"] = category
    else:
        args.setdefault("category", category)

    destination = brief.get("destination")
    if destination:
        args.setdefault("destination", destination)
    return args


def parse_json_response(raw: str) -> object:
    """
    Robustly extract JSON from an LLM response that may contain:
    - Leading/trailing prose
    - ```json ... ``` fences
    - Plain ``` ... ``` fences
    """
    raw = raw.strip()

    # Try direct parse first (cleanest case)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Extract from ```json ... ``` or ``` ... ``` fences
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Extract first JSON array or object found anywhere in the string
    for pattern in (r"(\[[\s\S]*\])", r"(\{[\s\S]*\})"):
        match = re.search(pattern, raw)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    raise ValueError(f"No valid JSON found in response: {raw[:200]}")
