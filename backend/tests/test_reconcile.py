"""Preference reconciliation (M-4).

The premise: embedding distance cannot separate agreement from contradiction.
Measured on real embeddings, a contradiction sits at 0.303 while an agreement
sits at 1.049 and two unrelated traits at 1.184 -- so any threshold is wrong in
both directions, and a model has to judge the pairs a threshold merely flags.
"""

import pytest

from app.reconcile import _CANDIDATE_MAX_DISTANCE, _candidate_pairs, _resolve


@pytest.fixture
def isolated_memory(monkeypatch):
    """Fresh in-memory Chroma collections, so these never touch a real profile.

    EphemeralClient shares a global in-process segment store, so collections must
    be deleted and recreated rather than trusting a new client to be clean.
    """
    import chromadb
    import app.memory as mem

    client = chromadb.EphemeralClient()
    for name in ("episodic", "semantic"):
        try:
            client.delete_collection(name)
        except Exception:
            pass
    semantic = client.get_or_create_collection("semantic")
    monkeypatch.setattr(mem, "_semantic", lambda: semantic)
    return semantic


OLD = "2026-09-01T00:00:00+00:00"
NEW = "2026-09-05T00:00:00+00:00"


def _row(row_id: str, text: str, created_at: str | None):
    return {"id": row_id, "text": text, "created_at": created_at}


# ── Resolution rules ────────────────────────────────────────────────────────

def test_contradiction_keeps_the_newer_statement():
    """Tastes change: the newer statement is the user's current position."""
    resolution = _resolve(
        _row("a", "prefers 3-day trips", OLD),
        _row("b", "prefers week-long trips", NEW),
        "contradiction", 0.303,
    )
    assert resolution.keep_text == "prefers week-long trips"
    assert resolution.drop_text == "prefers 3-day trips"


def test_duplicate_keeps_the_earlier_wording():
    """Recency carries no signal for a duplicate -- it only reflects when the
    extractor re-worded it. Observed live: re-extracting one conversation turned
    "does not drink alcohol" into the compressed "dislikes alcohol", and
    latest-wins would have kept the paraphrase over what the user actually said."""
    resolution = _resolve(
        _row("a", "does not drink alcohol", OLD),
        _row("b", "dislikes alcohol", NEW),
        "duplicate", 0.688,
    )
    assert resolution.keep_text == "does not drink alcohol"


def test_undated_row_loses_a_contradiction_but_wins_a_duplicate():
    """A row with no created_at predates M-2. It is unknown-age for a
    contradiction (so the dated, known-recent row wins) and older by construction
    for a duplicate (so it keeps the original phrasing)."""
    contradiction = _resolve(
        _row("a", "prefers 3-day trips", None),
        _row("b", "prefers week-long trips", NEW),
        "contradiction", 0.3,
    )
    assert contradiction.keep_text == "prefers week-long trips"

    duplicate = _resolve(
        _row("a", "does not drink alcohol", None),
        _row("b", "dislikes alcohol", NEW),
        "duplicate", 0.688,
    )
    assert duplicate.keep_text == "does not drink alcohol"


def test_two_undated_rows_are_left_alone():
    """Nothing distinguishes them, so resolving would be arbitrary."""
    assert _resolve(_row("a", "x", None), _row("b", "y", None), "duplicate", 0.5) is None


# ── Candidate selection ─────────────────────────────────────────────────────

def test_candidate_pairs_are_bounded_and_deduplicated(isolated_memory):
    """Pairs beyond the max distance are unrelated rather than in tension, and each
    unordered pair is asked about once rather than twice."""
    from app.memory import store_preferences, _semantic

    store_preferences([
        "does not drink alcohol",
        "enjoys museums and historic sites",
        "prefers walking and public transit",
    ])
    pairs = _candidate_pairs(_semantic())

    seen = {frozenset((a["id"], b["id"])) for a, b, _ in pairs}
    assert len(seen) == len(pairs), "each pair should appear once"
    assert all(d <= _CANDIDATE_MAX_DISTANCE for _, _, d in pairs)


def test_no_pairs_when_there_is_nothing_to_compare(isolated_memory):
    from app.memory import store_preferences, _semantic

    assert _candidate_pairs(_semantic()) == []
    store_preferences(["does not drink alcohol"])
    assert _candidate_pairs(_semantic()) == [], "one row cannot form a pair"


# ── Write-time supersede (the reversal case) ────────────────────────────────

def test_a_reversal_supersedes_rather_than_being_discarded(isolated_memory):
    """The sharp edge M-4 exposed: "prefers 3-day trips" and "prefers week-long
    trips" measure 0.303 apart, well inside the dedup threshold, so the write path
    saw the reversal as a near-duplicate. Keeping the stored text would silently
    discard the user changing their mind and preserve the stale opposite."""
    from app.memory import store_preferences, _semantic

    store_preferences(["prefers 3-day trips"])
    store_preferences(["prefers week-long trips"])

    assert _semantic().get()["documents"] == ["prefers week-long trips"]
    assert _semantic().count() == 1, "still one row -- superseded, not appended"


def test_superseding_does_not_merge_genuinely_distinct_traits(isolated_memory):
    from app.memory import store_preferences, _semantic

    store_preferences(["enjoys shopping and browsing"])
    store_preferences(["likes museums and historic sites"])

    assert _semantic().count() == 2
