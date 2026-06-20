"""
Voyager memory system — episodic and semantic memory via Chroma.

Episodic:  per-conversation summaries ("user asked about Tokyo, mentioned hating crowds")
Semantic:  distilled user preferences ("avoids crowded tourist areas", "loves street food")

Both collections use Chroma's default local embeddings (all-MiniLM-L6-v2), no API key needed.
The Chroma DB is persisted to ./chroma_db relative to where the server runs.
"""

import logging
import chromadb
from chromadb.config import Settings

logger = logging.getLogger("voyager.memory")

_client: chromadb.ClientAPI | None = None


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path="./chroma_db",
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
