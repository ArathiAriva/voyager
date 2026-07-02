import json
import re


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
