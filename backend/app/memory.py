"""
Voyager memory system — episodic and semantic memory via Chroma.

Episodic:  per-conversation summaries ("user asked about Tokyo, mentioned hating crowds")
Semantic:  distilled user preferences ("avoids crowded tourist areas", "loves street food")

Both collections use Chroma's default local embeddings (all-MiniLM-L6-v2), no API key needed.
The Chroma DB is persisted to ./chroma_db relative to where the server runs.
"""

import logging
import os
import chromadb
from chromadb.config import Settings

logger = logging.getLogger("voyager.memory")

_client: chromadb.ClientAPI | None = None
_CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")


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


def store_episode(conversation_id: str, summary: str) -> None:
    """Store a conversation summary as an episodic memory."""
    _episodic().upsert(ids=[conversation_id], documents=[summary])
    logger.info("memory | episodic stored for conv=%s", conversation_id[:8])


def store_preferences(preferences: list[str]) -> None:
    """Upsert extracted user preferences into semantic memory."""
    if not preferences:
        return
    collection = _semantic()
    for pref in preferences:
        # Use a deterministic ID so the same preference text deduplicates naturally
        pref_id = str(abs(hash(pref)))
        collection.upsert(ids=[pref_id], documents=[pref])
    logger.info("memory | %d preference(s) upserted", len(preferences))


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
    if count == 0:
        return []
    where = {"trip_id": trip_id} if trip_id else None
    kwargs: dict = {"query_texts": [query], "n_results": min(n_results, count)}
    if where:
        kwargs["where"] = where
    results = collection.query(**kwargs)
    hits = []
    if results["documents"]:
        for doc, meta, cid in zip(
            results["documents"][0],
            results["metadatas"][0],  # type: ignore[index]
            results["ids"][0],
        ):
            hits.append({
                "entry_id": cid,
                "destination": meta.get("destination", ""),
                "date": meta.get("date", ""),
                "text": doc,
            })
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
) -> list[dict]:
    collection = _places()
    count = collection.count()
    if count == 0:
        return []
    if trip_id and category:
        where: dict = {"$and": [{"trip_id": trip_id}, {"category": category}]}
    elif trip_id:
        where = {"trip_id": trip_id}
    elif category:
        where = {"category": category}
    else:
        where = {}
    kwargs: dict = {"query_texts": [query], "n_results": min(n_results, count)}
    if where:
        kwargs["where"] = where
    results = collection.query(**kwargs)
    hits = []
    if results["documents"]:
        for doc, meta, cid in zip(
            results["documents"][0],
            results["metadatas"][0],  # type: ignore[index]
            results["ids"][0],
        ):
            hits.append({
                "place_id": cid,
                "destination": meta.get("destination", ""),
                "name": meta.get("name", ""),
                "category": meta.get("category", ""),
                "text": doc,
            })
    logger.info("memory | places search '%s' → %d hits", query[:40], len(hits))
    return hits


def search_memory(query: str, n_results: int = 5) -> dict:
    """
    Search both episodic and semantic collections for memories relevant to the query.
    Returns a dict with 'episodes' and 'preferences' lists.
    """
    def _query(collection: chromadb.Collection) -> list[str]:
        count = collection.count()
        if count == 0:
            return []
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, count),
        )
        return results["documents"][0] if results["documents"] else []

    episodes = _query(_episodic())
    preferences = _query(_semantic())

    logger.info(
        "memory | search '%s' → %d episodes, %d preferences",
        query[:40], len(episodes), len(preferences),
    )
    return {"episodes": episodes, "preferences": preferences}
