from fastapi import APIRouter, Depends, HTTPException, Response

from app.schemas.clouds import CloudsResponse
from app.services.clouds import CloudsService, get_clouds_service

router = APIRouter(tags=["clouds"])


@router.get("/clouds", response_model=CloudsResponse, response_model_by_alias=True)
async def get_clouds(
    service: CloudsService = Depends(get_clouds_service),
) -> CloudsResponse:
    try:
        return await service.get_clouds()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to fetch cloud imagery") from exc


@router.get("/clouds/tiles/{z}/{x}/{y}.png")
async def get_cloud_tile(
    z: int,
    x: int,
    y: int,
    service: CloudsService = Depends(get_clouds_service),
) -> Response:
    if z < 0 or y < 0 or x < 0 or z > 12:
        raise HTTPException(status_code=400, detail="Invalid tile coordinates")
    try:
        png = await service.get_soft_tile(z, x, y)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to fetch cloud tile") from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=120"},
    )
