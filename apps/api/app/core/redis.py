from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

_redis_client: Redis | None = None


def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _redis_client


def check_redis_connection() -> bool:
    try:
        return get_redis().ping() is True
    except RedisError:
        return False


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None
