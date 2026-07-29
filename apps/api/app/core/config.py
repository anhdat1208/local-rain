from __future__ import annotations

import os
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Local Rain API"
    app_version: str = "0.1.0"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = (
        "postgresql+psycopg://localrain:localrain@localhost:5432/localrain"
    )
    # Vercel Upstash Storage usually exposes KV_URL (rediss://...); local uses REDIS_URL.
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("REDIS_URL", "KV_URL", "redis_url"),
    )
    cors_origins: str = "http://localhost:3000"
    # Browser-facing API base (cloud/radar tile proxy URLs).
    public_api_base: str = Field(
        default="http://localhost:8000",
        validation_alias=AliasChoices("PUBLIC_API_BASE", "public_api_base"),
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_public_api_base(self) -> str:
        base = (self.public_api_base or "").rstrip("/")
        if base and "localhost" not in base and "127.0.0.1" not in base:
            return base
        vercel_url = os.getenv("VERCEL_URL", "").strip()
        if vercel_url:
            if vercel_url.startswith("http"):
                return vercel_url.rstrip("/")
            return f"https://{vercel_url}"
        return base or "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
