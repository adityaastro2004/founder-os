from pydantic_settings import BaseSettings
from pydantic import model_validator
from functools import lru_cache
from pathlib import Path

# Minimum entropy for the workflow callback signing secret (O-2-AMEND / B-4).
# token_urlsafe(32) → 32 bytes → ≥43 URL-safe chars.
MIN_CALLBACK_SECRET_LEN = 43


ENV_FILE_PATH = Path(__file__).resolve().parent.parent / ".env"


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

    # ── Stripe Payments ──
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_STARTER_PRICE_ID: str = ""   # Monthly price ID from Stripe Dashboard
    STRIPE_PRO_PRICE_ID: str = ""
    STRIPE_ENTERPRISE_PRICE_ID: str = ""

    # App
    APP_ENV: str = "development"
    DEBUG: bool = False

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # ── Security middleware (app/security_middleware.py) ──
    SECURITY_HEADERS_ENABLED: bool = True
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 240      # per client per window
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    # The prod deployment sits behind a trusted front proxy (Vercel rewrite /
    # Caddy), so derive the client IP from X-Forwarded-For. Set False only when
    # the API is directly internet-exposed (XFF would then be attacker-spoofable).
    TRUST_PROXY: bool = True

    # ── Google Calendar Integration ──
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://127.0.0.1:8000/api/planner/connect/callback"
    OAUTH_STATE_SECRET: str = ""  # optional; falls back to GOOGLE_CLIENT_SECRET

    # ── Web Search (optional — for real web_search tool) ──
    SERPAPI_KEY: str = ""
    TAVILY_API_KEY: str = ""

    # ── Company State Engine (arch 2026-07-04 §11) ──
    STATE_DEDUP_SIM_THRESHOLD: float = 0.88
    STATE_WRITE_GATE_JUDGE_MAX_PER_SYNC: int = 10
    STATE_WRITE_GATE_JUDGE_TIMEOUT_S: int = 30
    STATE_OBSIDIAN_MAX_FILES: int = 5000
    STATE_OBSIDIAN_MAX_FILE_BYTES: int = 1_048_576

    # ── Notion adapter (arch 2026-07-07 §11) ──
    # Live-test-only credentials (B1): declared so a founder-populated .env can
    # never crash Settings() with extra_forbidden — which would kill API boot,
    # the worker, Alembic, AND echo the token into boot logs. The PRODUCT token
    # is never env; it lives on the integrations table (arch §2).
    NOTION_TEST_TOKEN: str = ""
    NOTION_TEST_ROOT_PAGE_ID: str = ""
    NOTION_ACCESS_TOKEN: str = ""  # founder-chosen alias accepted by the live suite
    STATE_NOTION_MAX_RPS: float = 3.0
    STATE_NOTION_MAX_RETRIES: int = 5
    STATE_NOTION_TIMEOUT_S: int = 30
    STATE_NOTION_MAX_OBJECTS: int = 2000
    STATE_NOTION_FULL_WALK_EVERY_S: int = 86_400
    STATE_NOTION_API_VERSION: str = "2022-06-28"

    # ── MCP Tool Servers ──
    # External MCP servers (stdio or SSE) to connect to.
    # Each entry: {"name": "...", "transport": "stdio"|"sse", "command": "...",
    #              "args": [...], "url": "...", "env": {}, "headers": {}}
    # In-process providers (Google Calendar) are auto-registered — no config needed.
    MCP_SERVERS: list[dict] = []

    # ── n8n + Workflow callbacks (Track B — ADR-008) ──
    # n8n REST connection (Track A wires the service; Track B reads these here).
    N8N_BASE_URL: str = "http://localhost:5678"
    N8N_API_KEY: str = ""
    # Where n8n HTTP nodes call back into Founder OS (the public-from-n8n base URL).
    WORKFLOW_CALLBACK_BASE_URL: str = "http://localhost:8000"
    # HMAC signing secret for per-workflow callback tokens (O-2). No usable default;
    # generate with: python -c "import secrets; print(secrets.token_urlsafe(32))".
    # Validated fail-fast below for any non-development environment.
    WORKFLOW_CALLBACK_SECRET: str = ""
    # Optional rollover slot for key rotation via `kid` (O-2-AMEND #3).
    WORKFLOW_CALLBACK_SECRET_PREVIOUS: str = ""

    model_config = {"env_file": str(ENV_FILE_PATH), "env_file_encoding": "utf-8"}

    @model_validator(mode="after")
    def _validate_callback_secret(self) -> "Settings":
        """
        Fail-fast on a weak/missing workflow callback secret (O-2-AMEND / B-4).

        Outside `development` the app MUST refuse to start if the secret is empty or
        shorter than 32 bytes of entropy (≥43 chars for token_urlsafe(32)). In
        `development` a missing secret is tolerated at startup (non-callback flows);
        the compiler enforces presence before compiling a workflow. Fail closed.
        """
        if self.APP_ENV != "development":
            secret = self.WORKFLOW_CALLBACK_SECRET or ""
            if len(secret) < MIN_CALLBACK_SECRET_LEN:
                raise ValueError(
                    "WORKFLOW_CALLBACK_SECRET must be set to at least 32 bytes of entropy "
                    f"(≥{MIN_CALLBACK_SECRET_LEN} chars) when APP_ENV != 'development'. "
                    'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))".'
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
