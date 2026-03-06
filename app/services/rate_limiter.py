from collections import defaultdict, deque
from datetime import datetime, timezone

from app.core.config import settings

try:
    import redis
except Exception:  # pragma: no cover - optional dependency path
    redis = None


class BaseRateLimiter:
    def is_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        raise NotImplementedError


class InMemoryRateLimiter(BaseRateLimiter):
    def __init__(self):
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        now_ts = datetime.now(timezone.utc).timestamp()
        window_start = now_ts - window_seconds

        bucket = self._buckets[key]
        while bucket and bucket[0] <= window_start:
            bucket.popleft()

        if len(bucket) >= limit:
            return False

        bucket.append(now_ts)
        return True


class RedisRateLimiter(BaseRateLimiter):
    def __init__(self, redis_url: str):
        if redis is None:
            raise RuntimeError("redis package is not installed")
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def is_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        redis_key = f"rate-limit:{key}"
        current = self._client.incr(redis_key)
        if current == 1:
            self._client.expire(redis_key, window_seconds)
        return current <= limit


def _build_rate_limiter() -> BaseRateLimiter:
    backend = (settings.AUTH_RATE_LIMIT_BACKEND or "memory").lower()
    if backend != "redis":
        return InMemoryRateLimiter()

    if not settings.AUTH_RATE_LIMIT_REDIS_URL:
        return InMemoryRateLimiter()

    try:
        limiter = RedisRateLimiter(settings.AUTH_RATE_LIMIT_REDIS_URL)
        limiter._client.ping()
        return limiter
    except Exception:
        return InMemoryRateLimiter()


rate_limiter = _build_rate_limiter()
