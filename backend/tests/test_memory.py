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

    # The query asks about food and transport, so those two traits come back and
    # the accommodation one (measured at 1.50, past the semantic floor) does not.
    # Retrieval used to pad to n_results and return all three regardless.
    assert set(results["preferences"]) == {"loves street food", "prefers walking over taxis"}


def test_irrelevant_preferences_are_not_padded_into_results():
    """Chroma returns n_results rows whenever the collection holds that many, so a
    query with nothing relevant still came back full. Every row here is unrelated to
    the query, so the honest answer is an empty list."""
    from app.memory import store_preferences, search_memory

    store_preferences(["prefers window seats", "collects fridge magnets"])
    results = search_memory("quantum chromodynamics")

    assert results["preferences"] == []


def test_empty_preferences_list_is_noop():
    from app.memory import store_preferences, search_memory

    store_preferences([])
    results = search_memory("anything")
    assert results["preferences"] == []


# ── Empty state ─────────────────────────────────────────────────────────────

def test_search_empty_collections_returns_empty():
    from app.memory import search_memory

    results = search_memory("solo travel Japan")
    assert results["episodes"] == []
    assert results["preferences"] == []
    # search_memory also returns id/distance hits now (retrieval spec); on empty
    # collections those are empty too.
    assert results["episode_hits"] == []
    assert results["preference_hits"] == []


# ── Combined ─────────────────────────────────────────────────────────────────

def test_search_returns_both_episodes_and_preferences():
    from app.memory import store_episode, store_preferences, search_memory

    store_episode("conv-x", "User planned a trip to Vietnam, loved the street food scene.")
    store_preferences(["prefers local markets over restaurants"])

    # Queried on the axis the preference is actually about. "Vietnam food" matches
    # the episode strongly but the preference only at 1.53 -- past the floor, so
    # asserting on it would be asserting on padding.
    results = search_memory("does the user like markets or restaurants")
    assert len(results["preferences"]) >= 1

    results = search_memory("Vietnam food")
    assert len(results["episodes"]) >= 1


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


# ── Place enrichment task lifetime (B-11) ───────────────────────────────────

def test_spawn_enrichment_keeps_a_strong_reference():
    """B-11: same defect class as B-1. Both enrichment call sites used a bare
    create_task, so the task could be GC'd mid-fetch -- leaving the place stuck at
    enrichment_status='pending' with no summary and no Chroma embedding, and so
    invisible to search_places."""
    import asyncio
    from app.routers import places

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_enrich(place_id, url, destination):
        started.set()
        await release.wait()

    async def scenario():
        original = places._enrich_place
        places._enrich_place = fake_enrich
        before = set(places._enrichment_tasks)
        try:
            places.spawn_enrichment("p1", "https://example.com", "Kyoto, Japan")
            await started.wait()
            added = set(places._enrichment_tasks) - before
            assert len(added) == 1
            release.set()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not (set(places._enrichment_tasks) & added)
        finally:
            places._enrich_place = original

    asyncio.run(scenario())


def test_enrichment_concurrency_is_bounded():
    """A bulk import must not fire unlimited outbound Jina fetches at once."""
    import asyncio
    from app.routers import places

    assert places._enrichment_semaphore._value == places._ENRICHMENT_CONCURRENCY
    assert places._ENRICHMENT_CONCURRENCY <= 8


# ── search_places tolerates a missing `query` ───────────────────────────────

def test_execute_search_places_without_query_does_not_raise(isolated_places):
    """`query` is schema-required but models omit it -- observed a live call with
    only {"destination": "Porto"}. A KeyError here propagated out of the tool
    loop and 500'd the whole conversation, so the turn was lost entirely."""
    import asyncio, json
    import app.memory as mem
    from app.tools import _execute_search_places

    mem.store_saved_place("p1", "trip-porto", "Porto, Portugal", "Mercado do Bolhao",
                          "restaurant", "Covered market with produce stalls.")

    out = json.loads(asyncio.run(_execute_search_places({"destination": "Porto"}, None)))
    assert "results" in out, out
    assert [r["name"] for r in out["results"]] == ["Mercado do Bolhao"]


# ── Conversation extraction task lifetime + concurrency (B-4) ───────────────

def test_conversation_spawn_extraction_keeps_a_strong_reference():
    """B-4: same defect class as B-1. A bare create_task can be GC'd mid-await,
    losing the extraction with no error. The task must be retained until done."""
    import asyncio
    from app.routers import conversations as conv

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_extract(conversation_id, history):
        started.set()
        await release.wait()

    async def scenario():
        original = conv._extract_and_store_memory
        conv._extract_and_store_memory = fake_extract
        before = set(conv._extraction_tasks)
        try:
            conv._spawn_extraction("c1", [])
            await started.wait()
            added = set(conv._extraction_tasks) - before
            assert len(added) == 1
            release.set()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not (set(conv._extraction_tasks) & added)
        finally:
            conv._extract_and_store_memory = original

    asyncio.run(scenario())


def test_conversation_extraction_is_concurrency_bounded():
    """B-4's other half: every exchange spawns an LLM-calling extraction, and
    nothing bounded how many ran at once. Background work should queue."""
    import asyncio
    from app.routers import conversations as conv

    async def scenario():
        peak = 0
        live = 0
        release = asyncio.Event()

        async def fake_run(conversation_id, history):
            nonlocal peak, live
            live += 1
            peak = max(peak, live)
            await release.wait()
            live -= 1

        original = conv._run_extraction
        conv._run_extraction = fake_run
        try:
            tasks = [
                asyncio.create_task(conv._extract_and_store_memory(f"c{i}", []))
                for i in range(conv._EXTRACTION_CONCURRENCY + 3)
            ]
            # Let everything that can start, start.
            for _ in range(10):
                await asyncio.sleep(0)
            assert peak <= conv._EXTRACTION_CONCURRENCY, f"peak={peak}"
            release.set()
            await asyncio.gather(*tasks)
        finally:
            conv._run_extraction = original

    asyncio.run(scenario())


# ── researcher scoping policy (R-1, guards B-6) ─────────────────────────────

def test_scope_search_args_defaults_category_and_destination():
    from app.agents import scope_search_args

    args = scope_search_args({}, {"destination": "Rome, Italy"}, category="restaurant")
    assert args == {"category": "restaurant", "destination": "Rome, Italy"}


def test_scope_search_args_respects_a_model_supplied_category():
    """food/activities let the model narrow within their domain."""
    from app.agents import scope_search_args

    args = scope_search_args({"category": "cafe"}, {"destination": "Rome"}, category="restaurant")
    assert args["category"] == "cafe"


def test_scope_search_args_can_force_the_category():
    """accommodation only ever wants hotels, and overwrote the model's choice."""
    from app.agents import scope_search_args

    args = scope_search_args({"category": "cafe"}, {"destination": "Rome"},
                             category="hotel", force_category=True)
    assert args["category"] == "hotel"


def test_scope_search_args_never_overrides_an_explicit_destination():
    from app.agents import scope_search_args

    args = scope_search_args({"destination": "Trastevere"}, {"destination": "Rome"},
                             category="restaurant")
    assert args["destination"] == "Trastevere"


def test_scope_search_args_without_a_destination_in_brief():
    """B-6: no destination scope is better than a wrong one, but the call must not fail."""
    from app.agents import scope_search_args

    args = scope_search_args({}, {}, category="restaurant")
    assert "destination" not in args
    assert args["category"] == "restaurant"


# ── eval harness profile adoption (R-3) ─────────────────────────────────────

def test_adopt_backend_database_redirects_the_engine(tmp_path, monkeypatch):
    """R-3: judge calls are usage-logged by the harness process, which resolved
    DATABASE_URL from root .env rather than the profile under test -- so a safetyeval
    run's costs were written to egwene.db. The harness must adopt whatever database
    the backend reports."""
    import asyncio
    import app.db as db
    from evals._harness import adopt_backend_database, profile_name

    backend_url = f"sqlite+aiosqlite:///{tmp_path}/under_test.db"
    wrong_url = f"sqlite+aiosqlite:///{tmp_path}/wrong.db"
    original = db.DB_PATH

    class FakeClient:
        async def get(self, path):
            assert path == "/health"
            class R:
                @staticmethod
                def json():
                    return {"status": "ok", "database_url": backend_url}
            return R()

    try:
        db.reconfigure(wrong_url)
        assert db.DB_PATH == wrong_url
        adopted = asyncio.run(adopt_backend_database(FakeClient()))
        assert adopted == backend_url
        assert db.DB_PATH == backend_url
    finally:
        db.reconfigure(original)


def test_adopt_backend_database_tolerates_an_older_backend():
    """A backend that does not report database_url must not break the run."""
    import asyncio
    import app.db as db
    from evals._harness import adopt_backend_database

    class FakeClient:
        async def get(self, path):
            class R:
                @staticmethod
                def json():
                    return {"status": "ok"}
            return R()

    before = db.DB_PATH
    assert asyncio.run(adopt_backend_database(FakeClient())) is None
    assert db.DB_PATH == before


def test_profile_name_reads_a_label_from_a_database_url():
    from evals._harness import profile_name

    assert profile_name("sqlite+aiosqlite:///./data/safetyeval.db") == "safetyeval"
    assert profile_name(None) == "unknown"


# ── shared SSE frame parsing (R-2) ──────────────────────────────────────────

SSE_SAMPLE = (
    "event: step\ndata: {\"label\": \"Researching activities...\"}\n\n"
    "event: error\ndata: {\"detail\": \"402 insufficient credits\"}\n\n"
    "event: done\ndata: {\"reply\": \"hi\"}\n"
)


def test_both_harnesses_surface_the_same_error_frame():
    """R-2: the two runners kept private copies of _parse_sse and drifted -- the
    safety one read `event: error` a day before the quality one, and in that window a
    402 was reported as an uninformative 'empty reply'. Both now share the frame
    parser, so this cannot diverge again."""
    from evals.run import _parse_sse as quality_parse
    from evals.safety_run import _parse_sse as safety_parse

    q_done, q_errors = quality_parse(SSE_SAMPLE)
    s_done, s_steps, s_errors = safety_parse(SSE_SAMPLE)

    assert q_done == s_done == {"reply": "hi"}
    assert q_errors == s_errors == ["402 insufficient credits"]
    assert s_steps == ["Researching activities..."]


def test_error_frame_falls_back_to_raw_text_when_not_json():
    from evals.run import _parse_sse as quality_parse
    from evals.safety_run import _parse_sse as safety_parse

    raw = "event: error\ndata: not json at all\n"
    assert quality_parse(raw)[1] == ["not json at all"]
    assert safety_parse(raw)[2] == ["not json at all"]


# ── retrieval instrumentation (docs/retrieval-quality-spec.md) ──────────────

def test_record_is_a_noop_without_a_running_loop():
    """Instrumentation must never dictate how callers are structured, and must never
    raise: an accounting failure cannot be allowed to break a user request."""
    from app import retrieval

    retrieval.record(collection="semantic", query="q", n_requested=5,
                     result_ids=["a"], distances=[0.1], latency_ms=1.0)


def test_record_writes_a_row_and_keeps_a_task_reference(tmp_path, monkeypatch):
    """The write is scheduled from sync code, so the task needs a strong reference
    or it can be garbage-collected mid-await (B-1/B-4/B-11)."""
    import asyncio
    import app.db as db
    from app import retrieval
    from app.models.orm import Base, RetrievalLogORM
    from sqlalchemy import select

    original = db.DB_PATH
    db.reconfigure(f"sqlite+aiosqlite:///{tmp_path}/retrieval.db")

    async def scenario():
        async with db.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        retrieval.record(collection="saved_places", query="where to eat",
                         n_requested=8, result_ids=["p1", "p2"],
                         distances=[0.31, 0.42], latency_ms=12.5,
                         filters={"destination": "Rome", "trip_id": None})
        assert len(retrieval._pending) == 1, "task must be retained while in flight"
        await asyncio.sleep(0.2)
        async with db.SessionLocal() as session:
            rows = (await session.execute(select(RetrievalLogORM))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.collection == "saved_places"
        assert row.n_requested == 8 and row.n_returned == 2
        assert row.result_ids == ["p1", "p2"]
        # None-valued filters are dropped, so "was a filter applied" stays meaningful
        assert row.filters == {"destination": "Rome"}
        assert not retrieval._pending, "task must be released once done"

    try:
        asyncio.run(scenario())
    finally:
        db.reconfigure(original)


def test_search_memory_returns_ids_and_distances():
    """Spec prerequisite: search_memory returned documents only, so its results were
    unauditable. Chroma provides ids and distances on every query."""
    import app.memory as mem

    mem.store_episode("conv-ret-1", "Walked the Palatine Hill at sunset.")
    out = mem.search_memory("what did I do in Rome")

    assert "episode_hits" in out and "preference_hits" in out
    assert out["episodes"] == [h["document"] for h in out["episode_hits"]]
    if out["episode_hits"]:
        hit = out["episode_hits"][0]
        assert hit["id"] and isinstance(hit["distance"], float)


def test_scoped_and_unscoped_place_searches_are_distinguishable(isolated_places):
    """The B-6 signature: an unscoped search spans destinations, a scoped one does
    not. Both are logged with their filters, so the difference is now measurable
    rather than something you notice by reading tool-call logs."""
    import app.memory as mem

    mem.store_saved_place("p-rome", "t1", "Rome, Italy", "Roscioli", "restaurant", "Roman pasta.")
    mem.store_saved_place("p-lis", "t2", "Lisbon, Portugal", "Licorista", "bar", "Ginjinha bar.")

    unscoped = mem.search_saved_places("where should I eat")
    scoped = mem.search_saved_places("where should I eat", destination="Rome")

    assert {h["destination"] for h in unscoped} == {"Rome, Italy", "Lisbon, Portugal"}
    assert {h["destination"] for h in scoped} == {"Rome, Italy"}


# ── Metadata provenance (M-2) ───────────────────────────────────────────────

def test_preferences_carry_provenance_metadata():
    """Rows previously had no metadata at all, which blocked recency-based
    contradiction handling (M-4), destination scoping (M-5), and tracing a bad
    preference back to the extraction that wrote it."""
    import app.memory as mem

    mem.store_preferences(["prefers night trains"], source="journal", destination="Lisbon, Portugal")
    row = mem._semantic().get(ids=[mem._preference_id("prefers night trains")])
    meta = row["metadatas"][0]

    assert meta["source"] == "journal"
    assert meta["destination"] == "Lisbon, Portugal"
    assert meta["created_at"]


def test_episodes_carry_provenance_metadata():
    import app.memory as mem

    mem.store_episode("conv-meta", "User asked about Porto.", source="conversation")
    meta = mem._episodic().get(ids=["conv-meta"])["metadatas"][0]

    assert meta["source"] == "conversation"
    assert meta["created_at"]


def test_destination_is_omitted_when_unknown():
    """Chroma rejects None metadata values, so an unknown destination must be left
    out of the dict rather than written as null."""
    import app.memory as mem

    mem.store_preferences(["prefers aisle seats"])
    meta = mem._semantic().get(ids=[mem._preference_id("prefers aisle seats")])["metadatas"][0]

    assert "destination" not in meta
    assert meta["source"] == "conversation"


# ── Multi-probe preference retrieval ────────────────────────────────────────

def test_merge_preference_hits_dedupes_and_ranks_by_best_distance():
    """Facet probes overlap, so the same row comes back from several of them. The
    merge keeps one copy at its best distance and ranks globally."""
    from app.agents.planner import _merge_preference_hits

    merged = _merge_preference_hits(
        [
            [{"id": "a", "document": "likes markets", "distance": 1.1},
             {"id": "b", "document": "likes trains", "distance": 0.9}],
            [{"id": "a", "document": "likes markets", "distance": 0.4}],
        ],
        limit=5,
    )

    assert merged == ["likes markets", "likes trains"]


def test_merge_preference_hits_respects_limit():
    from app.agents.planner import _merge_preference_hits

    hits = [{"id": str(i), "document": f"pref {i}", "distance": i / 10} for i in range(10)]
    assert _merge_preference_hits([hits], limit=3) == ["pref 0", "pref 1", "pref 2"]


def test_search_memory_can_target_one_collection():
    """The planner's facet probes want preferences only. Querying both collections
    would run six redundant episodic searches per plan and log six retrieval rows
    for searches nobody asked for."""
    from app.memory import store_episode, store_preferences, search_memory

    store_episode("conv-sel", "User asked about Porto.")
    store_preferences(["prefers guesthouses over hotels"])

    out = search_memory("accommodation preferences", collections=("semantic",))
    assert out["episodes"] == []
    assert out["episode_hits"] == []
    assert len(out["preferences"]) == 1


# ── Memories page: labelling and deletion ───────────────────────────────────

def test_memories_endpoint_tags_source_from_metadata():
    """The page labels each card chat/journal. Rows written since M-2 carry an
    explicit `source`, which is authoritative."""
    import asyncio
    from app.memory import store_episode, store_preferences
    from app.routers import memories as api

    store_episode("conv-1", "Chat about Porto.", source="conversation")
    store_episode("journal-abc", "Journal about Petra.", source="journal")
    store_preferences(["prefers guesthouses"], source="journal")

    out = asyncio.run(api.get_memories())
    by_text = {r["text"]: r["source"] for r in out["episode_rows"] + out["preference_rows"]}

    assert by_text["Chat about Porto."] == "chat"
    assert by_text["Journal about Petra."] == "journal"
    assert by_text["prefers guesthouses"] == "journal"


def test_memories_endpoint_falls_back_to_id_prefix_for_legacy_rows():
    """Rows written before M-2 have no metadata. Journal episodes are keyed
    `journal-{entry_id}`, which is the only signal available for them."""
    import asyncio
    import app.memory as mem
    from app.routers import memories as api

    # Write without metadata, as the pre-M-2 code did.
    mem._episodic().upsert(ids=["journal-legacy"], documents=["Old journal episode."])
    mem._episodic().upsert(ids=["conv-legacy"], documents=["Old chat episode."])

    out = asyncio.run(api.get_memories())
    by_text = {r["text"]: r["source"] for r in out["episode_rows"]}

    assert by_text["Old journal episode."] == "journal"
    assert by_text["Old chat episode."] == "chat"


def test_memories_endpoint_exposes_ids_for_deletion():
    """Bare documents were unaddressable -- the UI could not delete a specific row."""
    import asyncio
    from app.memory import store_preferences, _preference_id
    from app.routers import memories as api

    store_preferences(["prefers night trains"])
    out = asyncio.run(api.get_memories())

    assert out["preference_rows"][0]["id"] == _preference_id("prefers night trains")
    # Plain string lists stay for existing callers.
    assert out["preferences"] == ["prefers night trains"]


def test_delete_preference_removes_only_that_row():
    import asyncio
    from app.memory import store_preferences, _preference_id, search_memory
    from app.routers import memories as api

    store_preferences(["prefers night trains", "avoids early flights"])
    asyncio.run(api.delete_preference(_preference_id("prefers night trains")))

    remaining = search_memory("travel logistics", collections=("semantic",))["preferences"]
    assert "prefers night trains" not in remaining
    assert asyncio.run(api.get_memories())["preferences"] == ["avoids early flights"]


def test_delete_episode_removes_only_that_row():
    import asyncio
    from app.memory import store_episode
    from app.routers import memories as api

    store_episode("conv-1", "Chat about Porto.")
    store_episode("conv-2", "Chat about Lisbon.")
    asyncio.run(api.delete_episode("conv-1"))

    assert asyncio.run(api.get_memories())["episodes"] == ["Chat about Lisbon."]


def test_deleting_a_missing_memory_404s():
    """Chroma's delete is silent on a missing ID, so without an existence check the
    API would report success for a row it never removed."""
    import asyncio
    import pytest as _pytest
    from fastapi import HTTPException
    from app.routers import memories as api

    with _pytest.raises(HTTPException) as exc:
        asyncio.run(api.delete_episode("no-such-id"))
    assert exc.value.status_code == 404

    with _pytest.raises(HTTPException) as exc:
        asyncio.run(api.delete_preference("no-such-id"))
    assert exc.value.status_code == 404
