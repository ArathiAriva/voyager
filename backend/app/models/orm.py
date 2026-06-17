from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class TripORM(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    destination: Mapped[str] = mapped_column(String, nullable=False)
    dates: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    emoji: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(String, nullable=False, default="")
