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

    # ── LLM Providers ──
    LLM_PROVIDER: str = "ollama"  # "ollama" | "anthropic" | "openai_compatible"

    # Ollama (free, local — default)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # OpenAI-compatible (vLLM, Together, Groq, LM Studio, etc.)
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"

    # App
    APP_ENV: str = "development"
    DEBUG: bool = True

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
