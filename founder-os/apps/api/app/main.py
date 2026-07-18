import atexit
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from posthog import Posthog

from app.posthog_client import _set_posthog

from app.api.routes import router
from app.api.agent_routes import router as agent_router
from app.api.approval_routes import router as approval_router
from app.api.queue_routes import router as queue_router
from app.api.knowledge_routes import router as knowledge_router
from app.api.planner_routes import router as planner_router
from app.api.test_routes import router as test_router
from app.api.memory_routes import router as memory_router
from app.api.onboarding_routes import router as onboarding_router
from app.api.activity_routes import router as activity_router
from app.api.task_review_routes import router as review_router
from app.api.history_routes import router as history_router
from app.api.profile_routes import router as profile_router
from app.api.settings_routes import router as settings_router
from app.api.crawler_routes import router as crawler_router
from app.api.specialization_routes import router as specialization_router
from app.api.evolution_routes import router as evolution_router
from app.api.billing_routes import router as billing_router
from app.api.workflow_routes import router as workflow_router
from app.api.state_routes import router as state_router
from app.config import get_settings
from app.database import init_db, close_db
from app.redis import init_redis, close_redis
from app.scheduler import start_scheduler, stop_scheduler

# Configure root logging so app.* loggers print to console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

# Import models so they are registered with Base.metadata
import app.models  # noqa: F401
import app.planner_models_db  # noqa: F401
import app.state.models  # noqa: F401  — registers State Engine models (ADR-009)


async def _sync_agent_definitions() -> None:
    """Sync canonical agent prompts/capabilities from code → DB at startup (ADR-004).

    Best-effort: a failure here must not block startup (agents fall back to whatever
    is already in the DB).
    """
    from app.agents.registry import sync_agents_to_db
    from app.database import async_session

    try:
        async with async_session() as session:
            await sync_agents_to_db(session)
            await session.commit()
    except Exception:
        logging.getLogger(__name__).exception("Agent definition sync failed at startup")


_posthog_client: Posthog | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    global _posthog_client
    # ── Startup ──
    _settings = get_settings()
    if not _settings.POSTHOG_DISABLED and _settings.POSTHOG_PROJECT_TOKEN:
        _posthog_client = Posthog(
            api_key=_settings.POSTHOG_PROJECT_TOKEN,
            host=_settings.POSTHOG_HOST,
            enable_exception_autocapture=True,
        )
        _set_posthog(_posthog_client)
        atexit.register(_posthog_client.shutdown)

    await init_db()
    await _sync_agent_definitions()
    await init_redis()
    # Integration adapters (ADR-010): register once; callers use the registry.
    from app.integrations.google_calendar.adapter import register_adapter as register_gcal_adapter
    from app.integrations.notion.adapter import register_adapter as register_notion_adapter
    from app.integrations.obsidian.adapter import register_adapter as register_obsidian_adapter
    register_gcal_adapter()
    register_obsidian_adapter()
    register_notion_adapter()
    start_scheduler()
    yield
    # ── Shutdown ──
    stop_scheduler()
    await close_redis()
    await close_db()
    if _posthog_client is not None:
        _posthog_client.shutdown()


app = FastAPI(title="Founder OS API", lifespan=lifespan)

settings = get_settings()

# ── Fail-loud on a production misconfig ─────────────────
# When APP_ENV != "production" the unauthenticated dev test routes are mounted
# and the `x-test-user` auth bypass in app/auth.py is LIVE — anyone could
# impersonate any user. The deploy script pins APP_ENV=production; this warning
# makes an accidental dev-mode boot in a real environment impossible to miss.
if settings.APP_ENV != "production":
    logging.getLogger(__name__).warning(
        "APP_ENV=%r — dev test routes + x-test-user auth bypass are ACTIVE. "
        "This MUST be 'production' in any deployed environment.",
        settings.APP_ENV,
    )

# ── Security headers + rate limiting (app/security_middleware.py) ──
# CORS is added last and so stays the outermost layer; a 429 or a header-stamped
# error response therefore still gets CORS applied and is readable by the browser.
if settings.RATE_LIMIT_ENABLED:
    from app.security_middleware import RateLimitMiddleware

    app.add_middleware(
        RateLimitMiddleware,
        max_requests=settings.RATE_LIMIT_REQUESTS,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        trust_proxy=settings.TRUST_PROXY,
    )
if settings.SECURITY_HEADERS_ENABLED:
    from app.security_middleware import SecurityHeadersMiddleware

    app.add_middleware(SecurityHeadersMiddleware)

# ── CORS (needed for Clerk frontend → FastAPI calls) ────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(agent_router)
app.include_router(approval_router)
app.include_router(queue_router)
app.include_router(knowledge_router)
app.include_router(planner_router)
app.include_router(memory_router)
app.include_router(onboarding_router)
app.include_router(activity_router)
app.include_router(review_router)
app.include_router(history_router)
app.include_router(profile_router)
app.include_router(settings_router)
app.include_router(crawler_router)
app.include_router(specialization_router)
app.include_router(evolution_router)
app.include_router(billing_router)
app.include_router(workflow_router)
app.include_router(state_router)

# Dev-only test routes (no auth required)
if settings.APP_ENV == "development":
    app.include_router(test_router)


@app.get("/")
def root():
    return {"message": "Founder OS API running"}