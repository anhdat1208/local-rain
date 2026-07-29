from fastapi import APIRouter, Depends, Query

from app.schemas.nearest_rain import NearestRainResponse, RainVectorsResponse
from app.services.nearest_rain import NearestRainService, get_nearest_rain_service

router = APIRouter(tags=["nearest-rain"])


@router.get(
    "/nearest-rain",
    response_model=NearestRainResponse,
    response_model_by_alias=True,
)
async def get_nearest_rain(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    lang: str = Query("vi"),
    service: NearestRainService = Depends(get_nearest_rain_service),
) -> NearestRainResponse:
    return await service.find_nearest(lat, lng, lang=lang)


@router.get(
    "/rain-vectors",
    response_model=RainVectorsResponse,
    response_model_by_alias=True,
)
async def get_rain_vectors(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(100, ge=20, le=200),
    limit: int = Query(8, ge=1, le=16),
    service: NearestRainService = Depends(get_nearest_rain_service),
) -> RainVectorsResponse:
    return await service.find_vectors(lat, lng, radius_km=radius_km, limit=limit)
