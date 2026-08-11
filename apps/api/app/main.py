from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import dispose_engine
from app.core.http_client import close_http_client, get_http_client
from app.core.redis import close_redis
from app.routers import clouds, health, location, nearest_rain, radar


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Warm the shared connection pool so the first weather request isn't TLS-cold
    get_http_client()

    async def _warm_meta() -> None:
        try:
            from app.services.clouds import CloudsService
            from app.services.radar import RadarService

            await RadarService().get_radar_frames()
            await CloudsService().get_clouds()
        except Exception:
            return

    import asyncio

    asyncio.create_task(_warm_meta())
    yield
    await close_http_client()
    await close_redis()
    dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title="Local Rain API",
        version=settings.app_version,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health.router, prefix="/api")
    application.include_router(location.router, prefix="/api")
    application.include_router(radar.router, prefix="/api")
    application.include_router(clouds.router, prefix="/api")
    application.include_router(nearest_rain.router, prefix="/api")

    @application.get("/")
    def root() -> dict[str, str]:
        return {"service": "local-rain-api", "docs": "/docs"}

    return application


app = create_app()
