from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.db import SessionLocal
from app.models.orm import TripORM
from app.routers import chat, trips

app = FastAPI(title="Voyager API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api")
app.include_router(trips.router, prefix="/api")

_SEED_TRIPS = [
    TripORM(id="1", destination="Kyoto, Japan", dates="March 2025", status="past", emoji="🏯", summary="Cherry blossom season, temple walks, and too much matcha."),
    TripORM(id="2", destination="Lisbon, Portugal", dates="August 2025", status="past", emoji="🌊", summary="Fado evenings, pastéis de nata, and coastal sunsets."),
    TripORM(id="3", destination="Oaxaca, Mexico", dates="January 2026", status="upcoming", emoji="🌮", summary="Planning a deep dive into Zapotec culture and mezcal."),
]


@app.on_event("startup")
async def seed_trips() -> None:
    async with SessionLocal() as session:
        existing = await session.execute(select(TripORM).limit(1))
        if existing.scalar() is None:
            session.add_all(_SEED_TRIPS)
            await session.commit()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
