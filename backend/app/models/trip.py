from pydantic import BaseModel
from typing import Literal


class TripBase(BaseModel):
    destination: str
    dates: str
    status: Literal["past", "upcoming"]
    emoji: str
    summary: str = ""


class TripCreate(TripBase):
    pass


class TripUpdate(BaseModel):
    destination: str | None = None
    dates: str | None = None
    status: Literal["past", "upcoming"] | None = None
    emoji: str | None = None
    summary: str | None = None


class Trip(TripBase):
    id: str

    model_config = {"from_attributes": True}
