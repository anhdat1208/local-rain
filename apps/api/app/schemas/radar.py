from pydantic import BaseModel, ConfigDict, Field


class RadarFrameSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    timestamp: str
    unix_time: int = Field(alias="unixTime")
    tile_url_template: str = Field(alias="tileUrlTemplate")


class RadarResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    frames: list[RadarFrameSchema]
    generated_at: str = Field(alias="generatedAt")
    host: str
