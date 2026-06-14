from pydantic import BaseModel
from typing import Literal


class Trip(BaseModel):
    id: str
    destination: str
    dates: str
    status: Literal["past", "upcoming"]
    emoji: str
    summary: str
