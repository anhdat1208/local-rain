from pydantic import BaseModel, ConfigDict, Field


class CloudsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tile_url_template: str = Field(alias="tileUrlTemplate")
    timestamp: str
    source: str
    mode: str = Field(description="day = visible, night = infrared")
    max_zoom: int = Field(default=6, alias="maxZoom")
    attribution: str = "NASA GIBS / JMA Himawari"
