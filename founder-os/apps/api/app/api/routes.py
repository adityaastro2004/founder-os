from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth, optional_auth
from app.database import get_db
from app.redis import get_redis

router = APIRouter(prefix="/api")


# ── Public ───────────────────────────────────────────────
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


# ── Protected (require Clerk JWT) ────────────────────────
@router.get("/me")
async def get_current_user(user: ClerkUser = Depends(require_auth)):
    """Return the authenticated user's Clerk identity."""
    return {
        "user_id": user.user_id,
        "session_id": user.session_id,
        "org_id": user.org_id,
        "org_role": user.org_role,
        "email": user.email,
    }


# ── Optional auth example ───────────────────────────────
@router.get("/greet")
async def greet(user: ClerkUser | None = Depends(optional_auth)):
    """Public endpoint that personalises response if the user is logged in."""
    if user:
        return {"message": f"Hello, {user.email or user.user_id}!"}
    return {"message": "Hello, guest!"}