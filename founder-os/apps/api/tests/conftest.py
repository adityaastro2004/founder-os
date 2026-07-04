"""Test bootstrap: make the unit tier runnable with zero services configured.

Values mirror .github/workflows/ci.yml — they satisfy config parsing only;
unit tests must never open a DB/Redis/LLM connection.
"""
import os

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://founder:founder@localhost:5432/founder_os")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql+psycopg2://founder:founder@localhost:5432/founder_os")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("LLM_PROVIDER", "ollama")
