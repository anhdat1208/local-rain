from pydantic import BaseModel, Field


class LocationResponse(BaseModel):
    latitude: float
    longitude: float
    label: str = Field(examples=["District 8"])
