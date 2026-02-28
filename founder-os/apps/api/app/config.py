from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://founder:founder@localhost:5432/founder_os"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://founder:founder@localhost:5432/founder_os"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # App
    APP_ENV: str = "development"
    DEBUG: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
