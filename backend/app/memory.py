"""
Voyager memory system — episodic and semantic memory via Chroma.

Episodic:  per-conversation summaries ("user asked about Tokyo, mentioned hating crowds")
Semantic:  distilled user preferences ("avoids crowded tourist areas", "loves street food")

Both collections use Chroma's default local embeddings (all-MiniLM-L6-v2), no API key needed.
The Chroma DB is persisted to ./chroma_db relative to where the server runs.
"""

import hashlib
import logging
import os
import time
from datetime import datetime, timezone
import chromadb
from chromadb.config import Settings

from app import retrieval
from app.utils import dest_matches

logger = logging.getLogger("voyager.memory")

_client: chromadb.ClientAPI | None = None
_CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")

# Drop hits beyond this L2 distance instead of padding the result out to n_results.
#
# Chroma always returns exactly n_results rows if the collection holds that many, so
# `search_memory` could never say "nothing relevant" -- it returned five rows because
# it was asked for five. A logged planning query ("I plan to be there between 11am and
# 6pm") came back with five preferences at distances 1.24-1.53, none of them a real
# match, and the planner handed all five to the critic as stated user intent.
#
# The floor is per-collection because the collections hold different *kinds* of text
# and so sit in different distance regimes. Preferences and episodes are sentences
# ("prefers guesthouses over hotels") that embed close to a natural-language query.
# Saved places are short noun phrases ("Roman pasta.") which embed far from a full
# question no matter how relevant they are -- measured against the live collections,
# "dinner recommendations" over 13 real saved restaurants bottoms out at 1.57. A
# single 1.30 floor would return nothing there, which is a worse failure than the
# padding it was meant to fix.
#
# Calibrated on live egwene/rand/moiraine data. For semantic/episodic, genuine
# matches land at or under ~1.25 ("street food" -> 0.24, "budget" -> 0.77) while
# padding sits at 1.35+. Saved places get a looser bound because `destination`
# already does the real scoping there (B-6); the floor is only a backstop against
# a wholly unrelated query.
#
# All of this is specific to all-MiniLM-L6-v2 L2 distances -- changing the embedding
# model means recalibrating every number here.
_DEFAULT_MAX_DISTANCE = 1.30
_MAX_DISTANCE_BY_COLLECTION = {
    "semantic": 1.30,
    "episodic": 1.30,
    "journals": 1.45,
    "saved_places": 1.75,
}


def _max_distance(collection: str) -> float:
    """Distance floor for a collection, overridable per-collection via env.

    VOYAGER_MAX_RETRIEVAL_DISTANCE sets a global override;
    VOYAGER_MAX_RETRIEVAL_DISTANCE_SEMANTIC (etc.) sets one collection.
    """
    specific = os.getenv(f"VOYAGER_MAX_RETRIEVAL_DISTANCE_{collection.upper()}")
    if specific:
        return float(specific)
    override = os.getenv("VOYAGER_MAX_RETRIEVAL_DISTANCE")
    if override:
        return float(override)
    return _MAX_DISTANCE_BY_COLLECTION.get(collection, _DEFAULT_MAX_DISTANCE)


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=_CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def _episodic() -> chromadb.Collection:
    return _get_client().get_or_create_collection("episodic")


def _semantic() -> chromadb.Collection:
    return _get_client().get_or_create_collection("semantic")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def store_episode(
    conversation_id: str,
    summary: str,
    source: str = "conversation",
    destination: str | None = None,
) -> None:
    """Store a conversation summary as an episodic memory."""
    meta: dict = {"created_at": _now(), "source": source}
    if destination:
        meta["destination"] = destination
    _episodic().upsert(ids=[conversation_id], documents=[summary], metadatas=[meta])
    logger.info("memory | episodic stored for conv=%s", conversation_id[:8])


def _preference_id(pref: str) -> str:
    """Content-addressed ID for a preference string.

    Must be stable across processes: Python's built-in hash() is salted per
    process (PYTHONHASHSEED), so the previous `str(abs(hash(pref)))` produced a
    different ID for identical text on every server restart and defeated the
    upsert dedup it was meant to provide. Normalising case and whitespace also
    collapses near-identical rows that differ only in capitalisation.
    """
    normalized = " ".join(pref.split()).lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def store_preferences(
    preferences: list[str],
    source: str = "conversation",
    destination: str | None = None,
) -> None:
    """Upsert extracted user preferences into semantic memory.

    Every row carries `created_at`, `source`, and (when known) `destination`.
    Rows previously had no metadata at all, which blocked everything downstream:
    contradictions could not be resolved by recency, a bad preference could not be
    traced to the extraction that produced it, and a destination-locked trait like
    "enjoys traditional Portuguese cuisine" was retrieved with full authority when
    planning Tokyo. Chroma metadata is schemaless, so no migration is needed, and
    the M-1 purge means there is nothing to backfill -- rows carry it from the
    first write.

    `destination` is recorded but deliberately not yet used as a retrieval filter.
    Scoping (M-5) needs a policy for the durable/conditional split -- "prefers
    street food" learned in Lisbon should stay global -- and that decision wants
    live data behind it rather than a guess made at write time.
    """
    if not preferences:
        return
    collection = _semantic()
    meta: dict = {"created_at": _now(), "source": source}
    if destination:
        meta["destination"] = destination
    for pref in preferences:
        collection.upsert(ids=[_preference_id(pref)], documents=[pref], metadatas=[meta])
    logger.info("memory | %d preference(s) upserted (source=%s)", len(preferences), source)


def _delete_by_id(collection: chromadb.Collection, memory_id: str, label: str) -> bool:
    """Delete one row, returning False if it wasn't there.

    Chroma's `delete` is silent on a missing ID, so existence is checked first --
    the caller needs to distinguish "removed" from "never existed" to return 404
    rather than a misleading success.
    """
    existing = collection.get(ids=[memory_id])
    if not (existing.get("ids") or []):
        logger.info("memory | %s delete missed: id=%s not found", label, memory_id[:16])
        return False
    collection.delete(ids=[memory_id])
    logger.info("memory | %s deleted: id=%s", label, memory_id[:16])
    return True


def delete_episode(memory_id: str) -> bool:
    """Remove one episodic memory. Returns False if no such row."""
    return _delete_by_id(_episodic(), memory_id, "episodic")


def delete_preference(memory_id: str) -> bool:
    """Remove one learned preference. Returns False if no such row.

    Preference IDs are content hashes (`_preference_id`), which is what makes this
    possible at all: under the old per-process `abs(hash())` scheme no caller could
    recompute the ID a previous process had written, so no stored preference could
    be addressed, corrected, or forgotten.
    """
    return _delete_by_id(_semantic(), memory_id, "semantic")


def _journals() -> chromadb.Collection:
    return _get_client().get_or_create_collection("journals")


def store_journal_entry(entry_id: str, trip_id: str, destination: str, date: str, body: str) -> None:
    """Embed a journal entry for RAG retrieval."""
    _journals().upsert(
        ids=[entry_id],
        documents=[body],
        metadatas=[{"trip_id": trip_id, "destination": destination, "date": date}],
    )
    logger.info("memory | journal entry embedded: entry=%s trip=%s", entry_id[:8], trip_id[:8])


def delete_journal_entry(entry_id: str) -> None:
    """Remove a journal entry from the vector store."""
    try:
        _journals().delete(ids=[entry_id])
        logger.info("memory | journal entry removed: entry=%s", entry_id[:8])
    except Exception:
        logger.warning("memory | could not delete journal entry %s (may not exist)", entry_id[:8])


def search_journals(query: str, trip_id: str | None = None, n_results: int = 5) -> list[dict]:
    """
    Search journal entries semantically.
    Optionally scoped to a single trip via trip_id.
    Returns a list of dicts with keys: entry_id, destination, date, text.
    """
    collection = _journals()
    count = collection.count()
    filters = {"trip_id": trip_id}
    if count == 0:
        retrieval.record(collection="journals", query=query, n_requested=n_results,
                         result_ids=[], distances=[], latency_ms=0.0, filters=filters)
        return []
    where = {"trip_id": trip_id} if trip_id else None
    kwargs: dict = {"query_texts": [query], "n_results": min(n_results, count)}
    if where:
        kwargs["where"] = where
    started = time.perf_counter()
    results = collection.query(**kwargs)
    latency_ms = (time.perf_counter() - started) * 1000
    hits = []
    kept_distances: list[float] = []
    if results["documents"]:
        raw_distances = results["distances"][0] if results.get("distances") else []
        for idx, (doc, meta, cid) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0],  # type: ignore[index]
            results["ids"][0],
        )):
            distance = raw_distances[idx] if idx < len(raw_distances) else None
            if distance is not None and distance > _max_distance("journals"):
                continue
            hits.append({
                "entry_id": cid,
                "destination": meta.get("destination", ""),
                "date": meta.get("date", ""),
                "text": doc,
            })
            if distance is not None:
                kept_distances.append(distance)
    retrieval.record(collection="journals", query=query, n_requested=n_results,
                     result_ids=[h["entry_id"] for h in hits],
                     distances=kept_distances,
                     latency_ms=latency_ms, filters=filters)
    logger.info("memory | journal search '%s' → %d hits", query[:40], len(hits))
    return hits


def _places() -> chromadb.Collection:
    return _get_client().get_or_create_collection("saved_places")


def store_saved_place(
    place_id: str, trip_id: str, destination: str, name: str, category: str, text: str
) -> None:
    """Embed a saved place for RAG retrieval."""
    _places().upsert(
        ids=[place_id],
        documents=[text],
        metadatas=[{"trip_id": trip_id, "destination": destination, "name": name, "category": category}],
    )
    logger.info("memory | saved place embedded: place=%s trip=%s", place_id[:8], trip_id[:8])


def delete_saved_place(place_id: str) -> None:
    try:
        _places().delete(ids=[place_id])
        logger.info("memory | saved place removed: place=%s", place_id[:8])
    except Exception:
        logger.warning("memory | could not delete saved place %s (may not exist)", place_id[:8])


def search_saved_places(
    query: str,
    trip_id: str | None = None,
    category: str | None = None,
    n_results: int = 8,
    destination: str | None = None,
) -> list[dict]:
    """Semantic search over saved places.

    `destination` scopes results to one place-name, e.g. "Rome" won't return
    saved places from Lisbon. It exists because the planning researchers have no
    trip_id to filter on: for a fresh plan the trip doesn't exist yet (it's
    resolved/created at persist time, see planning/graph.py), so destination is
    the only scope available while research is running. Without it, planning a
    Rome trip retrieves every saved restaurant the user has anywhere.

    Matching is fuzzy ("Rome" ~ "Rome, Italy") via utils.dest_matches, which
    Chroma's `where` cannot express, so it is applied after the query. To keep
    the post-filter from starving the result set, the vector search over-fetches
    and the caller's n_results is applied to the filtered hits.
    """
    collection = _places()
    count = collection.count()
    filters = {"trip_id": trip_id, "category": category, "destination": destination}
    if count == 0:
        retrieval.record(collection="saved_places", query=query, n_requested=n_results,
                         result_ids=[], distances=[], latency_ms=0.0, filters=filters)
        return []
    if trip_id and category:
        where: dict = {"$and": [{"trip_id": trip_id}, {"category": category}]}
    elif trip_id:
        where = {"trip_id": trip_id}
    elif category:
        where = {"category": category}
    else:
        where = {}
    # Over-fetch when a destination filter will be applied after the query, so
    # near-matches from other destinations don't crowd out the ones we want.
    fetch = min(count, n_results * 5 if destination else n_results)
    kwargs: dict = {"query_texts": [query], "n_results": fetch}
    if where:
        kwargs["where"] = where
    started = time.perf_counter()
    results = collection.query(**kwargs)
    latency_ms = (time.perf_counter() - started) * 1000
    hits = []
    kept_distances: list[float] = []
    if results["documents"]:
        raw_distances = results["distances"][0] if results.get("distances") else []
        for idx, (doc, meta, cid) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0],  # type: ignore[index]
            results["ids"][0],
        )):
            place_dest = meta.get("destination", "")
            if destination and not dest_matches(destination, place_dest):
                continue
            distance = raw_distances[idx] if idx < len(raw_distances) else None
            if distance is not None and distance > _max_distance("saved_places"):
                continue
            hits.append({
                "place_id": cid,
                "destination": place_dest,
                "name": meta.get("name", ""),
                "category": meta.get("category", ""),
                "text": doc,
            })
            if idx < len(raw_distances):
                kept_distances.append(raw_distances[idx])
            if len(hits) >= n_results:
                break
    # Log post-filter hits: the destination scope is applied after the vector query,
    # and it is exactly what B-6 got wrong, so the filtered result is the meaningful
    # one to measure.
    retrieval.record(collection="saved_places", query=query, n_requested=n_results,
                     result_ids=[h["place_id"] for h in hits], distances=kept_distances,
                     latency_ms=latency_ms, filters=filters)
    logger.info("memory | places search '%s'%s → %d hits", query[:40],
                f" [dest={destination}]" if destination else "", len(hits))
    return hits


def search_memory(
    query: str,
    n_results: int = 5,
    collections: tuple[str, ...] = ("episodic", "semantic"),
) -> dict:
    """
    Search both episodic and semantic collections for memories relevant to the query.
    Returns a dict with 'episodes' and 'preferences' lists.

    Also returns 'episode_hits'/'preference_hits' carrying each document's Chroma ID
    and distance. The plain lists stay for existing callers; the hits make a result
    auditable and measurable after the fact, which it previously was not -- Chroma
    returns ids and distances on every query and they were being discarded.

    `collections` narrows the search. The planner's facet probes want preferences
    only; without this they would run six redundant episodic queries per plan and
    write six misleading `retrieval_log` rows for searches nobody asked for.
    """
    def _query(collection: chromadb.Collection, name: str) -> list[dict]:
        count = collection.count()
        if count == 0:
            retrieval.record(collection=name, query=query, n_requested=n_results,
                             result_ids=[], distances=[], latency_ms=0.0)
            return []
        started = time.perf_counter()
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, count),
        )
        latency_ms = (time.perf_counter() - started) * 1000
        documents = results["documents"][0] if results["documents"] else []
        ids = results["ids"][0] if results.get("ids") else []
        distances = results["distances"][0] if results.get("distances") else []
        hits = [
            {"id": i, "document": d, "distance": dist}
            for i, d, dist in zip(ids, documents, distances)
            if dist <= _max_distance(name)
        ]
        dropped = len(ids) - len(hits)
        if dropped:
            logger.info(
                "memory | %s: dropped %d/%d hit(s) past distance %.2f for '%s'",
                name, dropped, len(ids), _max_distance(name), query[:40],
            )
        # Record what the caller actually received, not what Chroma offered -- the
        # log is meant to reflect retrieval as the model experiences it.
        retrieval.record(collection=name, query=query, n_requested=n_results,
                         result_ids=[h["id"] for h in hits],
                         distances=[h["distance"] for h in hits],
                         latency_ms=latency_ms)
        return hits

    episode_hits = _query(_episodic(), "episodic") if "episodic" in collections else []
    preference_hits = _query(_semantic(), "semantic") if "semantic" in collections else []
    episodes = [h["document"] for h in episode_hits]
    preferences = [h["document"] for h in preference_hits]

    logger.info(
        "memory | search '%s' → %d episodes, %d preferences",
        query[:40], len(episodes), len(preferences),
    )
    return {
        "episodes": episodes,
        "preferences": preferences,
        "episode_hits": episode_hits,
        "preference_hits": preference_hits,
    }
