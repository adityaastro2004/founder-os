from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.redis import get_redis

router = APIRouter(prefix="/api")


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_db),
):
    """Check API, PostgreSQL, and Redis connectivity."""
    checks: dict = {"api": "ok"}

    # PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"

    # Redis
    try:
        redis = get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    healthy = all(v == "ok" for v in checks.values())
    return {"healthy": healthy, "checks": checks}