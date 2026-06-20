"""
Tests for the memory module (episodic + semantic storage and retrieval).

Uses an in-memory Chroma client so tests don't touch the persistent ./chroma_db
and don't require the embedding model to be downloaded.
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def isolated_memory(monkeypatch):
    """
    Isolate each test by wiping and recreating the Chroma collections.
    EphemeralClient uses a global in-process segment store, so new client instances
    don't give a clean slate — we must delete + recreate collections explicitly.
    """
    import chromadb
    import app.memory as mem

    client = chromadb.EphemeralClient()

    for name in ("episodic", "semantic"):
        try:
            client.delete_collection(name)
        except Exception:
            pass
    episodic_col = client.get_or_create_collection("episodic")
    semantic_col = client.get_or_create_collection("semantic")

    monkeypatch.setattr(mem, "_episodic", lambda: episodic_col)
    monkeypatch.setattr(mem, "_semantic", lambda: semantic_col)
    yield


# ── Episodic ────────────────────────────────────────────────────────────────

def test_store_and_retrieve_episode():
    from app.memory import store_episode, search_memory

    store_episode("conv-1", "User asked about solo hiking in Patagonia.")
    results = search_memory("hiking trip")

    assert len(results["episodes"]) == 1
    assert "Patagonia" in results["episodes"][0]


def test_episode_upsert_replaces_existing():
    from app.memory import store_episode, search_memory

    store_episode("conv-1", "User asked about Paris cafés.")
    store_episode("conv-1", "User updated — now asking about Lyon restaurants.")

    results = search_memory("France food")
    assert len(results["episodes"]) == 1
    assert "Lyon" in results["episodes"][0]


def test_multiple_episodes_returned_by_relevance():
    from app.memory import store_episode, search_memory

    store_episode("conv-a", "User asked about beach resorts in Thailand.")
    store_episode("conv-b", "User asked about ski resorts in Austria.")
    store_episode("conv-c", "User asked about safari in Kenya.")

    results = search_memory("tropical beach holiday")
    # Thailand episode should rank first
    assert "Thailand" in results["episodes"][0]


# ── Semantic ────────────────────────────────────────────────────────────────

def test_store_and_retrieve_preference():
    from app.memory import store_preferences, search_memory

    store_preferences(["prefers boutique hotels over large chains"])
    results = search_memory("accommodation style")

    assert len(results["preferences"]) == 1
    assert "boutique" in results["preferences"][0]


def test_preference_deduplication():
    from app.memory import store_preferences, search_memory

    store_preferences(["avoids tourist traps"])
    store_preferences(["avoids tourist traps"])  # same text → same hash ID → upsert

    results = search_memory("tourist areas")
    assert len(results["preferences"]) == 1


def test_multiple_preferences_stored():
    from app.memory import store_preferences, search_memory

    prefs = [
        "loves street food",
        "prefers walking over taxis",
        "avoids all-inclusive resorts",
    ]
    store_preferences(prefs)
    results = search_memory("food and transport preferences")

    assert len(results["preferences"]) == 3


def test_empty_preferences_list_is_noop():
    from app.memory import store_preferences, search_memory

    store_preferences([])
    results = search_memory("anything")
    assert results["preferences"] == []


# ── Empty state ─────────────────────────────────────────────────────────────

def test_search_empty_collections_returns_empty():
    from app.memory import search_memory

    results = search_memory("solo travel Japan")
    assert results == {"episodes": [], "preferences": []}


# ── Combined ─────────────────────────────────────────────────────────────────

def test_search_returns_both_episodes_and_preferences():
    from app.memory import store_episode, store_preferences, search_memory

    store_episode("conv-x", "User planned a trip to Vietnam, loved the street food scene.")
    store_preferences(["prefers local markets over restaurants"])

    results = search_memory("Vietnam food")
    assert len(results["episodes"]) >= 1
    assert len(results["preferences"]) >= 1
