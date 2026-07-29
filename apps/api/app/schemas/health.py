from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    postgres: bool
    redis: bool
    version: str = Field(examples=["0.1.0"])
