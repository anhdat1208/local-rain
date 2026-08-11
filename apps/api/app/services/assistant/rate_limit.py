from __future__ import annotations

from app.core.redis import get_redis


class RateLimitExceeded(Exception):
    pass


def check_rate_limit(client_ip: str, *, limit: int, window_seconds: int) -> None:
    key = f"assistant:rate:{client_ip or 'unknown'}"
    try:
        redis = get_redis()
        count = redis.incr(key)
        if count == 1:
            redis.expire(key, window_seconds)
        if count > limit:
            raise RateLimitExceeded()
    except RateLimitExceeded:
        raise
    except Exception:
        # If Redis is down, allow the request rather than blocking the product.
        return
