from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://founder:founder@localhost:5432/founder_os"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://founder:founder@localhost:5432/founder_os"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Clerk Auth
    CLERK_ISSUER: str = ""  # e.g. https://<your-clerk-instance>.clerk.accounts.dev
    CLERK_JWKS_URL: str = ""  # e.g. https://<your-clerk-instance>.clerk.accounts.dev/.well-known/jwks.json
    CLERK_AUDIENCE: str = ""  # optional — leave empty to skip audience check

    # App
    APP_ENV: str = "development"
    DEBUG: bool = True

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
