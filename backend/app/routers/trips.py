from fastapi import APIRouter
from app.models.trip import Trip

router = APIRouter(prefix="/trips", tags=["trips"])

_TRIPS: list[Trip] = [
    Trip(
        id="1",
        destination="Kyoto, Japan",
        dates="March 2025",
        status="past",
        emoji="🏯",
        summary="Cherry blossom season, temple walks, and too much matcha.",
    ),
    Trip(
        id="2",
        destination="Lisbon, Portugal",
        dates="August 2025",
        status="past",
        emoji="🌊",
        summary="Fado evenings, pastéis de nata, and coastal sunsets.",
    ),
    Trip(
        id="3",
        destination="Oaxaca, Mexico",
        dates="January 2026",
        status="upcoming",
        emoji="🌮",
        summary="Planning a deep dive into Zapotec culture and mezcal.",
    ),
]


@router.get("", response_model=list[Trip])
async def list_trips() -> list[Trip]:
    return _TRIPS
