from fastapi import APIRouter, HTTPException
from app import memory as mem

router = APIRouter(prefix="/memories", tags=["memories"])


def _source_of(memory_id: str, metadata: dict | None) -> str:
    """Where a memory came from: "chat" or "journal".

    Prefers the `source` metadata written since M-2 (2026-09-04). Rows written
    before that carry no metadata, so fall back to the ID convention: journal
    episodes are keyed `journal-{entry_id}`, conversation episodes by raw
    conversation_id. Preferences have no such prefix, so an old preference row
    reports "chat" -- the common case, and the only guess available.
    """
    if metadata and metadata.get("source"):
        return "journal" if metadata["source"] == "journal" else "chat"
    return "journal" if memory_id.startswith("journal-") else "chat"


def _rows(collection) -> list[dict]:
    """Flatten a Chroma collection into id/text/source/created_at rows.

    IDs are the point: the previous version returned bare `documents`, so the UI
    could neither tell a journal-derived episode from a conversation one nor
    address a specific row to delete it.
    """
    if collection.count() == 0:
        return []
    raw = collection.get()
    ids = raw.get("ids") or []
    documents = raw.get("documents") or []
    metadatas = raw.get("metadatas") or [None] * len(ids)
    rows = [
        {
            "id": memory_id,
            "text": document,
            "source": _source_of(memory_id, metadata),
            "created_at": (metadata or {}).get("created_at"),
        }
        for memory_id, document, metadata in zip(ids, documents, metadatas)
    ]
    # Newest first, but only rows written since M-2 have created_at; undated rows
    # sort last rather than being dropped or claiming a false date.
    rows.sort(key=lambda r: (r["created_at"] is not None, r["created_at"] or ""), reverse=True)
    return rows


@router.get("")
async def get_memories() -> dict:
    """Return all stored episodic and semantic memories from Chroma.

    `episodes`/`preferences` stay as plain string lists for existing callers;
    `episode_rows`/`preference_rows` carry the id, source and timestamp the
    Memories page needs to label and delete individual entries.
    """
    episode_rows = _rows(mem._episodic())
    preference_rows = _rows(mem._semantic())

    return {
        "episodes": [r["text"] for r in episode_rows],
        "preferences": [r["text"] for r in preference_rows],
        "episode_rows": episode_rows,
        "preference_rows": preference_rows,
    }


@router.delete("/episodic/{memory_id}", status_code=204)
async def delete_episode(memory_id: str) -> None:
    """Forget one episodic memory.

    Deleting the episode does not delete the conversation or journal entry it was
    distilled from -- this removes what Voyager remembers, not the source record.
    Note a journal episode will be recreated if its entry is edited, since PATCH
    re-runs extraction.
    """
    if not mem.delete_episode(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")


@router.delete("/semantic/{memory_id}", status_code=204)
async def delete_preference(memory_id: str) -> None:
    """Forget one learned preference.

    Preferences are re-derived from conversations and journal entries, so a trait
    the user keeps demonstrating can come back on a later extraction. This deletes
    the stored row, not the behaviour that produced it.
    """
    if not mem.delete_preference(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
