# Founder OS API — production image.
# Same image runs the FastAPI server AND the Celery worker (command is overridden
# per service in docker-compose.prod.yml). Build context = apps/api.
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build deps for asyncpg / psycopg2 (libpq) + curl for the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

# Default = API server (1 worker; APScheduler runs in-process so do NOT scale >1).
# The worker service overrides this with the celery command.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
