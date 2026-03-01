from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@asynccontextmanager
async def lifespan(application: FastAPI):
    # ── Startup ──
    await init_db()
    await init_redis()
    start_scheduler()
    yield
    # ── Shutdown ──
    stop_scheduler()
    await close_redis()
    await close_db()


app = FastAPI(title="Founder OS API", lifespan=lifespan)

# ── CORS (needed for Clerk frontend → FastAPI calls) ────
settings = get_settings()
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

# Dev-only test routes (no auth required)
if settings.APP_ENV == "development":
    app.include_router(test_router)


@app.get("/")
def root():
    return {"message": "Founder OS API running"}