from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
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

app.include_router(router)


@app.get("/")
def root():
    return {"message": "Founder OS API running"}