import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DB_PATH = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./voyager.db")

engine = create_async_engine(DB_PATH, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
