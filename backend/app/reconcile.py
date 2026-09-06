"""Semantic contradiction reconciliation for stored preferences (M-4).

`store_preferences` dedupes *re-wordings* at write time by embedding distance
(M-3). That is the right tool for "prefers walking and public transit over other
transportation" vs "prefers walking or public transit over driving", which are
the same trait typed twice.

It is the wrong tool for contradiction, and measurably so. Distance does not
separate agreement from conflict:

    CONTRADICT  0.303   'prefers 3-day trips'       vs 'prefers week-long trips'
    AGREE       0.688   'does not drink alcohol'    vs 'dislikes alcohol'
    CONTRADICT  0.971   'prefers early starts'      vs 'prefers slow lazy mornings'
    AGREE       1.049   'enjoys street food'        vs 'loves cheap local eats'
    DISTINCT    1.184   'enjoys shopping'           vs 'likes museums'
    CONTRADICT  1.272   'travels on a tight budget' vs 'enjoys luxury hotels'

A contradiction can be closer than a re-wording, and an agreement further apart
than two unrelated traits. Any threshold gets both cases wrong, in both
directions -- so this asks a model, and only about pairs a threshold has already
flagged as *possibly* related.

Cost is bounded by construction: candidate pairs come from a nearest-neighbour
query per row, one LLM call reconciles a whole batch, and it runs on demand
rather than on the write path. `store_preferences` stays synchronous and
LLM-free.

Resolution uses the `created_at` M-2 added, and the rule differs by verdict:
**contradictions keep the newer** row (tastes change, and the newer statement is
the user's current position), while **duplicates keep the older** (recency there
reflects only when the extractor re-worded it, not anything about the user). See
`_resolve`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app import memory
from app.claude import get_client, get_model
from app.usage import usage_context

logger = logging.getLogger("voyager.reconcile")

# Pairs further apart than this are not worth asking about: at 1.30+ the two
# statements are unrelated rather than in tension (measured above -- the widest
# real contradiction was 1.272). The floor is the write-time dedup threshold,
# since anything below it never became two rows in the first place.
_CANDIDATE_MIN_DISTANCE = memory._PREFERENCE_DUPLICATE_DISTANCE
_CANDIDATE_MAX_DISTANCE = 1.30

RECONCILE_PROMPT = """You are reconciling a user's stored travel preferences.

Each numbered pair holds two preferences that may or may not conflict. For each
pair decide:

- "contradiction" — both cannot be true of the same traveller at the same time.
  ("prefers 3-day trips" vs "prefers week-long trips")
- "duplicate" — they say the same thing in different words.
  ("does not drink alcohol" vs "dislikes alcohol")
- "compatible" — different traits, or a nuance, that can both be true.
  ("enjoys street food" vs "enjoys fine dining occasionally")

Respond with JSON only, no prose:
{"verdicts": [{"pair": 1, "verdict": "contradiction|duplicate|compatible"}]}

Be conservative: answer "compatible" unless the conflict or the redundancy is
clear. A traveller can hold preferences that merely sit in tension — liking both
budget hostels and the occasional splurge is normal, not a contradiction."""


@dataclass(frozen=True)
class Resolution:
    """One reconciliation decision, ready to apply."""

    keep_id: str
    keep_text: str
    drop_id: str
    drop_text: str
    verdict: str  # "contradiction" | "duplicate"
    distance: float


def _candidate_pairs(collection) -> list[tuple[dict, dict, float]]:
    """Preference pairs close enough to be worth asking a model about.

    Deduplicated on the unordered id pair, so A~B is asked once rather than twice.
    """
    raw = collection.get()
    ids, documents, metadatas = raw["ids"], raw["documents"], raw["metadatas"] or []
    if len(ids) < 2:
        return []

    by_id = {
        i: {"id": i, "text": d, "created_at": (m or {}).get("created_at")}
        for i, d, m in zip(ids, documents, list(metadatas) + [None] * len(ids))
    }

    seen: set[frozenset] = set()
    pairs: list[tuple[dict, dict, float]] = []
    for document in documents:
        results = collection.query(query_texts=[document], n_results=min(4, len(ids)))
        source_id = next((i for i, r in by_id.items() if r["text"] == document), None)
        if source_id is None:
            continue
        for other_id, distance in zip(results["ids"][0], results["distances"][0]):
            if other_id == source_id:
                continue
            if not (_CANDIDATE_MIN_DISTANCE <= distance <= _CANDIDATE_MAX_DISTANCE):
                continue
            key = frozenset((source_id, other_id))
            if key in seen or other_id not in by_id:
                continue
            seen.add(key)
            pairs.append((by_id[source_id], by_id[other_id], distance))
    return pairs


def _resolve(a: dict, b: dict, verdict: str, distance: float) -> Resolution | None:
    """Decide which row of a judged pair survives.

    **Contradiction: latest wins.** The two statements disagree, so the newer one
    is the user's current position and supersedes the older.

    **Duplicate: earliest wins.** They say the same thing, so recency carries no
    signal about the user at all -- it only reflects when the extractor happened to
    re-word it. Keeping the first phrasing matches the write-time dedup, which
    skips an incoming near-duplicate rather than replacing the stored row, and it
    keeps the wording closest to what the user originally said. Observed live:
    re-extracting one conversation turned "does not drink alcohol" into the
    compressed "dislikes alcohol"; latest-wins would have kept the paraphrase.

    A row with no `created_at` predates M-2. It loses a contradiction (the dated
    row is known-recent) and wins a duplicate (it is the older phrasing). Two
    undated rows are left alone rather than resolved arbitrarily.
    """
    a_time, b_time = a.get("created_at"), b.get("created_at")
    if a_time is None and b_time is None:
        return None

    if verdict == "duplicate":
        # Undated is the older row by construction, so it survives.
        if a_time is None:
            keep, drop = a, b
        elif b_time is None:
            keep, drop = b, a
        else:
            keep, drop = (a, b) if a_time <= b_time else (b, a)
    else:
        if a_time is None:
            keep, drop = b, a
        elif b_time is None:
            keep, drop = a, b
        else:
            keep, drop = (a, b) if a_time >= b_time else (b, a)

    return Resolution(keep["id"], keep["text"], drop["id"], drop["text"], verdict, distance)


async def reconcile_preferences(apply: bool = False, max_pairs: int = 40) -> list[Resolution]:
    """Find and optionally resolve contradictory or duplicate preferences.

    Returns the resolutions. With `apply=False` (the default) nothing is deleted,
    so this is safe to call for inspection. One LLM call for the whole batch.
    """
    collection = memory._semantic()
    pairs = _candidate_pairs(collection)[:max_pairs]
    if not pairs:
        logger.info("reconcile | no candidate pairs")
        return []

    listing = "\n".join(
        f'{n}. A: "{a["text"]}"\n   B: "{b["text"]}"'
        for n, (a, b, _) in enumerate(pairs, start=1)
    )
    usage_context.set("memory_extraction")
    response = await get_client().chat.completions.create(
        model=get_model(),
        messages=[
            {"role": "system", "content": RECONCILE_PROMPT},
            {"role": "user", "content": listing},
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        verdicts = json.loads(raw).get("verdicts", [])
    except json.JSONDecodeError:
        logger.warning("reconcile | unparseable judge response: %r", raw[:200])
        return []

    resolutions: list[Resolution] = []
    for verdict in verdicts:
        index = verdict.get("pair", 0) - 1
        label = verdict.get("verdict")
        if not (0 <= index < len(pairs)) or label not in ("contradiction", "duplicate"):
            continue
        a, b, distance = pairs[index]
        resolution = _resolve(a, b, label, distance)
        if resolution:
            resolutions.append(resolution)

    for resolution in resolutions:
        logger.info("reconcile | %s (d=%.3f): keep %r, drop %r",
                    resolution.verdict, resolution.distance,
                    resolution.keep_text[:50], resolution.drop_text[:50])
        if apply:
            memory.delete_preference(resolution.drop_id)

    logger.info("reconcile | %d pair(s) judged, %d resolution(s)%s",
                len(pairs), len(resolutions), " applied" if apply else " (dry run)")
    return resolutions
