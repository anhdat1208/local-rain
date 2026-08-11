from fastapi import APIRouter, Depends, Query

from app.schemas.location import LocationResponse
from app.services.geocoding import GeocodingService, get_geocoding_service

router = APIRouter(tags=["location"])


@router.get("/location", response_model=LocationResponse)
async def get_location(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lng: float = Query(..., ge=-180, le=180, description="Longitude"),
    lang: str = Query("vi", description="Label language (vi|en)"),
    geocoding: GeocodingService = Depends(get_geocoding_service),
) -> LocationResponse:
    label = await geocoding.reverse_geocode(lat, lng, lang=lang)
    return LocationResponse(latitude=lat, longitude=lng, label=label)
