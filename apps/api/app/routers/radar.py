from fastapi import APIRouter, Depends, HTTPException, Response

from app.schemas.radar import RadarResponse
from app.services.radar import RadarService, get_radar_service

router = APIRouter(tags=["radar"])


@router.get("/radar", response_model=RadarResponse, response_model_by_alias=True)
async def get_radar(
    radar_service: RadarService = Depends(get_radar_service),
) -> RadarResponse:
    try:
        return await radar_service.get_radar_frames()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to fetch radar frames") from exc


@router.get("/radar/tiles/{unix_time}/{z}/{x}/{y}.png")
async def get_radar_tile(
    unix_time: int,
    z: int,
    x: int,
    y: int,
    radar_service: RadarService = Depends(get_radar_service),
) -> Response:
    if z < 0 or z > 7 or x < 0 or y < 0 or unix_time < 0:
        raise HTTPException(status_code=400, detail="Invalid tile coordinates")
    try:
        png = await radar_service.get_filtered_tile(unix_time, z, x, y)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to fetch radar tile") from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=120"},
    )
