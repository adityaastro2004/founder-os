import redis.asyncio as redis

from app.config import get_settings

settings = get_settings()

redis_client: redis.Redis | None = None


async def init_redis() -> redis.Redis:
    """Create and return the global Redis client."""
    global redis_client
    redis_client = redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
    # Verify connectivity
    await redis_client.ping()
    return redis_client


async def close_redis() -> None:
    """Gracefully close the Redis connection."""
    global redis_client
    if redis_client:
        await redis_client.aclose()
        redis_client = None


def get_redis() -> redis.Redis:
    """FastAPI dependency that returns the Redis client."""
    if redis_client is None:
        raise RuntimeError("Redis is not initialised. Call init_redis() first.")
    return redis_client
