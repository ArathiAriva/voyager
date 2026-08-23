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


# ── Saved-place retrieval scoping (B-6) ─────────────────────────────────────

@pytest.fixture
def isolated_places(monkeypatch):
    """Fresh `places` collection, separate from the autouse episodic/semantic one."""
    import chromadb
    import app.memory as mem

    client = chromadb.EphemeralClient()
    try:
        client.delete_collection("places")
    except Exception:
        pass
    col = client.get_or_create_collection("places")
    monkeypatch.setattr(mem, "_places", lambda: col)
    return col


def _seed_places(mem):
    mem.store_saved_place("p1", "trip-rome", "Rome, Italy", "Roscioli", "restaurant",
                          "Deli and restaurant near Campo de' Fiori.")
    mem.store_saved_place("p2", "trip-lis", "Lisbon, Portugal", "A Licorista", "restaurant",
                          "Traditional tile-covered restaurant, pork dishes.")
    mem.store_saved_place("p3", "trip-ist", "Istanbul, Turkey", "Neolokal", "restaurant",
                          "Fine dining, farm-to-table Turkish cuisine.")


def test_search_saved_places_unscoped_returns_all_destinations(isolated_places):
    """Baseline: without a destination filter, retrieval spans every trip."""
    import app.memory as mem
    _seed_places(mem)
    hits = mem.search_saved_places("great restaurant", category="restaurant")
    assert {h["name"] for h in hits} == {"Roscioli", "A Licorista", "Neolokal"}


def test_search_saved_places_scopes_to_destination(isolated_places):
    """B-6: a Rome plan must not retrieve Lisbon/Istanbul saved places."""
    import app.memory as mem
    _seed_places(mem)
    hits = mem.search_saved_places("great restaurant", category="restaurant",
                                   destination="Rome, Italy")
    assert [h["name"] for h in hits] == ["Roscioli"]


def test_search_saved_places_destination_match_is_fuzzy(isolated_places):
    """The brief says 'Rome'; the saved place says 'Rome, Italy'. Must still match."""
    import app.memory as mem
    _seed_places(mem)
    hits = mem.search_saved_places("great restaurant", destination="Rome")
    assert [h["name"] for h in hits] == ["Roscioli"]


def test_search_saved_places_unknown_destination_returns_nothing(isolated_places):
    import app.memory as mem
    _seed_places(mem)
    assert mem.search_saved_places("great restaurant", destination="Osaka, Japan") == []


def test_search_saved_places_respects_n_results_after_filtering(isolated_places):
    """Over-fetching for the post-filter must not overshoot the caller's limit."""
    import app.memory as mem
    for i in range(5):
        mem.store_saved_place(f"r{i}", "trip-rome", "Rome, Italy", f"Trattoria {i}",
                              "restaurant", "Roman pasta and wine.")
    mem.store_saved_place("l1", "trip-lis", "Lisbon, Portugal", "A Licorista",
                          "restaurant", "Portuguese tiles and pork.")
    hits = mem.search_saved_places("pasta", destination="Rome", n_results=3)
    assert len(hits) == 3
    assert all(h["destination"] == "Rome, Italy" for h in hits)


# ── Journal extraction task lifetime (B-1) ──────────────────────────────────

def test_spawn_extraction_keeps_a_strong_reference():
    """B-1: a bare create_task can be GC'd mid-flight, losing the extraction
    silently. _spawn_extraction must hold a reference until the task finishes."""
    import asyncio
    from app.routers import journal

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_extract(entry_id, dest, body):
        started.set()
        await release.wait()

    async def scenario():
        original = journal._extract_journal_memory
        journal._extract_journal_memory = fake_extract
        # Other tests in the suite hit the journal API and leave their own
        # extraction tasks in this module-global set, so assert on the delta
        # rather than absolute size.
        before = set(journal._extraction_tasks)
        try:
            journal._spawn_extraction("e1", "Rome", "body")
            await started.wait()
            # While in flight the task must be retained, or nothing keeps it alive.
            added = set(journal._extraction_tasks) - before
            assert len(added) == 1
            release.set()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            # ...and released once done, so the set can't grow without bound.
            assert not (set(journal._extraction_tasks) & added)
        finally:
            journal._extract_journal_memory = original

    asyncio.run(scenario())
