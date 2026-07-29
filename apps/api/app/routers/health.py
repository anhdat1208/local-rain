from fastapi import APIRouter

from app.core.database import check_database_connection
from app.core.redis import check_redis_connection
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    # Postgres is optional on Vercel — Redis cache is the dependency that matters.
    postgres_ok = check_database_connection()
    redis_ok = check_redis_connection()

    if redis_ok:
        status = "ok"
    elif postgres_ok:
        status = "degraded"
    else:
        status = "error"

    return HealthResponse(
        status=status,
        postgres=postgres_ok,
        redis=redis_ok,
        version="0.1.0",
    )
