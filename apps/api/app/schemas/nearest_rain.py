from pydantic import BaseModel, ConfigDict, Field

from app.utils.geo import CompassDirection


class NearestRainResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    distance: float
    eta: int = 0
    direction: CompassDirection
    confidence: int = Field(ge=0, le=100)
    explanation: str
    advice: str = ""
    has_rain: bool = Field(alias="hasRain")
    rain_latitude: float | None = Field(default=None, alias="rainLatitude")
    rain_longitude: float | None = Field(default=None, alias="rainLongitude")
    motion_direction: CompassDirection | None = Field(default=None, alias="motionDirection")
    speed_kmh: float = Field(default=0, alias="speedKmh")
    approaching: bool = False
    previous_distance: float | None = Field(default=None, alias="previousDistance")
    rain_chance: str = Field(default="none", alias="rainChance")
    rain_chance_pct: int = Field(default=0, alias="rainChancePct", ge=0, le=100)
    rain_in_1h: bool = Field(default=False, alias="rainIn1h")
    rain_in_2h: bool = Field(default=False, alias="rainIn2h")
    raining_here: bool = Field(default=False, alias="rainingHere")
    radar_timestamp: str | None = Field(default=None, alias="radarTimestamp")
    radar_age_minutes: int = Field(default=0, alias="radarAgeMinutes", ge=0)
    sky_state: str = Field(default="clear", alias="skyState")
    cloud_cover_pct: int = Field(default=0, alias="cloudCoverPct", ge=0, le=100)


class RainVectorItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    latitude: float
    longitude: float
    to_latitude: float = Field(alias="toLatitude")
    to_longitude: float = Field(alias="toLongitude")
    speed_kmh: float = Field(alias="speedKmh")
    direction: CompassDirection
    dbz: float = Field(ge=0, le=75)


class RainVectorsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vectors: list[RainVectorItem]
    generated_at: str = Field(alias="generatedAt")
