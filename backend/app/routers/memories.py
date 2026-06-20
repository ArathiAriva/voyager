from fastapi import APIRouter
from app import memory as mem

router = APIRouter(prefix="/memories", tags=["memories"])


@router.get("")
async def get_memories() -> dict:
    """Return all stored episodic and semantic memories from Chroma."""
    episodic = mem._episodic()
    semantic = mem._semantic()

    episodes = episodic.get()["documents"] or [] if episodic.count() > 0 else []
    preferences = semantic.get()["documents"] or [] if semantic.count() > 0 else []

    return {"episodes": episodes, "preferences": preferences}
