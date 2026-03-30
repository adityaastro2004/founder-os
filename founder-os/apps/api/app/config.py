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
    LLM_PROVIDER: str = "ollama"  # "ollama" | "anthropic" | "openai_compatible" | "gemini"

    # Ollama (free, local — default)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # OpenAI-compatible (Groq — fast open-source LLM inference)
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.groq.com/openai/v1"
    OPENAI_MODEL: str = "llama-3.3-70b-versatile"

    # Gemini (Google)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # ── Embedding Provider ──
    EMBEDDING_PROVIDER: str = "ollama"  # "ollama" | "openai"
    EMBEDDING_MODEL: str = "nomic-embed-text"  # Ollama default
    EMBEDDING_API_KEY: str = ""  # Only needed for OpenAI
    EMBEDDING_BASE_URL: str = ""  # Falls back to OLLAMA_BASE_URL or OpenAI default
    EMBEDDING_DIMENSIONS: int = 1536  # Padded/truncated to match pgvector column

    # App
    APP_ENV: str = "development"
    DEBUG: bool = False

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # ── Google Calendar Integration ──
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://127.0.0.1:8000/api/planner/connect/callback"

    # ── Web Search (optional — for real web_search tool) ──
    SERPAPI_KEY: str = ""
    TAVILY_API_KEY: str = ""

    # ── MCP Tool Servers ──
    # External MCP servers (stdio or SSE) to connect to.
    # Each entry: {"name": "...", "transport": "stdio"|"sse", "command": "...",
    #              "args": [...], "url": "...", "env": {}, "headers": {}}
    # In-process providers (Google Calendar) are auto-registered — no config needed.
    MCP_SERVERS: list[dict] = []

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
