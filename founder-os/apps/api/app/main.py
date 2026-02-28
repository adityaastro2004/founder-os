from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.agent_routes import router as agent_router
from app.api.approval_routes import router as approval_router
from app.api.queue_routes import router as queue_router
from app.config import get_settings
from app.database import init_db, close_db
from app.redis import init_redis, close_redis

# Import models so they are registered with Base.metadata
import app.models  # noqa: F401


@asynccontextmanager
async def lifespan(application: FastAPI):
    # ── Startup ──
    await init_db()
    await init_redis()
    yield
    # ── Shutdown ──
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


@app.get("/")
def root():
    return {"message": "Founder OS API running"}