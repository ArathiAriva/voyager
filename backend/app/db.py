import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DB_PATH = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./voyager.db")

engine = create_async_engine(DB_PATH, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


def reconfigure(database_url: str) -> None:
    """Re-point the engine at a different database at runtime.

    Only for out-of-process tooling (the eval harnesses, R-3), which learn the
    backend's real database from /health after this module has already been imported.
    The server itself never calls this -- it reads DATABASE_URL once at startup.
    """
    global DB_PATH, engine, SessionLocal

    if database_url == DB_PATH:
        return
    DB_PATH = database_url
    engine = create_async_engine(DB_PATH, echo=False)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
