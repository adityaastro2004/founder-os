from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=30,
    pool_recycle=1800,       # recycle connections after 30 min
    pool_pre_ping=True,      # verify connections before checkout
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an async DB session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Verify the database connection on startup.

    Tables are managed via Alembic migrations + schema.sql,
    so we only do a lightweight connectivity check here.
    """
    async with engine.begin() as conn:
        await conn.execute(
            __import__("sqlalchemy").text("SELECT 1")
        )


async def close_db() -> None:
    """Dispose of the connection pool."""
    await engine.dispose()
