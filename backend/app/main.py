from dotenv import load_dotenv
load_dotenv()

import logging
import logging.config

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "loggers": {
        "voyager": {"level": "DEBUG", "handlers": ["console"], "propagate": False},
        # Silence noisy libraries
        "sqlalchemy.engine": {"level": "WARNING"},
        "httpx": {"level": "WARNING"},
    },
})

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.db import SessionLocal, engine, Base
from app.models.orm import TripORM
import app.models.orm  # noqa: F401 — ensure all ORM models are registered on Base.metadata
from app.routers import trips, conversations, journal, content, memories, places

app = FastAPI(title="Voyager API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trips.router, prefix="/api")
app.include_router(conversations.router, prefix="/api")
app.include_router(journal.router, prefix="/api")
app.include_router(content.router, prefix="/api")
app.include_router(memories.router, prefix="/api")
app.include_router(places.router, prefix="/api")

_SEED_TRIPS = [
    TripORM(id="1", destination="Kyoto, Japan", dates="March 2025", status="past", emoji="🏯", summary="Cherry blossom season, temple walks, and too much matcha."),
    TripORM(id="2", destination="Lisbon, Portugal", dates="August 2025", status="past", emoji="🌊", summary="Fado evenings, pastéis de nata, and coastal sunsets."),
    TripORM(id="3", destination="Oaxaca, Mexico", dates="January 2026", status="upcoming", emoji="🌮", summary="Planning a deep dive into Zapotec culture and mezcal."),
]


@app.on_event("startup")
async def startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        existing = await session.execute(select(TripORM).limit(1))
        if existing.scalar() is None:
            session.add_all(_SEED_TRIPS)
            await session.commit()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
