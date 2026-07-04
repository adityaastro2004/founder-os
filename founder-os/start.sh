#!/bin/bash
# start.sh - Start the complete Founder OS stack
# Usage: ./start.sh          (start everything)
#        ./start.sh --stop   (stop everything)

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

# ── n8n workflow engine (ADR-008 O-4: default-on, profile-disable-able) ──
# n8n ships behind the "n8n" compose profile so `docker compose up` stays lean.
# start.sh activates that profile by default; set FOS_DISABLE_N8N=1 to opt out
# (the zero-cost laptop path — Postgres + Redis only).
if [[ "${FOS_DISABLE_N8N:-0}" == "1" ]]; then
  export COMPOSE_PROFILES=""
else
  export COMPOSE_PROFILES="n8n"
fi

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log()  { echo -e "${CYAN}[Founder OS]${NC} $1"; }
ok()   { echo -e "${GREEN}  ✔${NC} $1"; }
warn() { echo -e "${YELLOW}  ⚠${NC} $1"; }
err()  { echo -e "${RED}  ✖${NC} $1"; }

# ── Cleanup function ──
cleanup() {
  echo ""
  log "Shutting down..."
  # Kill background processes
  [[ -n "$CELERY_PID" ]] && kill "$CELERY_PID" 2>/dev/null && ok "Celery worker stopped"
  [[ -n "$API_PID" ]] && kill "$API_PID" 2>/dev/null && ok "API server stopped"
  [[ -n "$WEB_PID" ]] && kill "$WEB_PID" 2>/dev/null && ok "Web dev server stopped"
  docker compose --profile n8n down 2>/dev/null && ok "Docker services stopped"
  exit 0
}

# ── Stop mode ──
if [[ "$1" == "--stop" ]]; then
  log "Stopping all services..."
  # Kill any running Celery worker
  pkill -f 'celery.*worker' 2>/dev/null && ok "Celery worker stopped" || warn "No Celery worker found"
  # Kill any running uvicorn on port 8000
  lsof -ti :8000 | xargs kill -9 2>/dev/null && ok "API server stopped" || warn "No API server found on :8000"
  # Kill any running next dev on port 3000
  lsof -ti :3000 | xargs kill -9 2>/dev/null && ok "Web dev server stopped" || warn "No web server found on :3000"
  docker compose --profile n8n down 2>/dev/null && ok "Docker services stopped" || warn "Docker services not running"
  exit 0
fi

trap cleanup SIGINT SIGTERM

echo ""
echo -e "${CYAN} Founder OS  -  Start ${NC}"
echo ""

# ── 1. Check prerequisites ──
log "Checking prerequisites..."

if ! command -v docker &>/dev/null; then
  err "Docker is not installed. Please install Docker Desktop: https://docker.com"
  exit 1
fi

if ! docker info &>/dev/null; then
  err "Docker daemon is not running. Please start Docker Desktop and try again."
  exit 1
fi
ok "Docker is running"

if ! command -v node &>/dev/null; then
  err "Node.js is not installed."
  exit 1
fi
ok "Node.js $(node -v)"

if [[ ! -d "apps/api/.venv" ]]; then
  err "Python venv not found at apps/api/.venv"
  err "Run: cd apps/api && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi
ok "Python venv found"

# ── Optional: Google Calendar OAuth config check ──
GOOGLE_ENV_FILE="apps/api/.env"
if [[ -f "$GOOGLE_ENV_FILE" ]]; then
  missing_google_vars=()
  for k in GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET GOOGLE_REDIRECT_URI OAUTH_STATE_SECRET; do
    line=$(grep -E "^${k}=" "$GOOGLE_ENV_FILE" | tail -n 1 || true)
    val="${line#*=}"
    if [[ -z "$line" || -z "$val" ]]; then
      missing_google_vars+=("$k")
    fi
  done

  if [[ ${#missing_google_vars[@]} -gt 0 ]]; then
    warn "Google Calendar connect unavailable (missing in $GOOGLE_ENV_FILE): ${missing_google_vars[*]}"
  else
    ok "Google Calendar OAuth env looks configured"
  fi
else
  warn "No apps/api/.env found; Google Calendar connect will be unavailable"
fi

# ── 2. Start Docker services (PostgreSQL + Redis [+ n8n]) ──
if [[ -n "$COMPOSE_PROFILES" ]]; then
  log "Starting PostgreSQL, Redis & n8n..."
else
  log "Starting PostgreSQL & Redis (n8n disabled via FOS_DISABLE_N8N)..."
fi
docker compose up -d

# Wait for PostgreSQL to be healthy
log "Waiting for PostgreSQL to be ready..."
RETRIES=30
until docker compose exec -T postgres pg_isready -U founder -d founder_os &>/dev/null; do
  RETRIES=$((RETRIES - 1))
  if [[ $RETRIES -le 0 ]]; then
    err "PostgreSQL did not become ready in time."
    exit 1
  fi
  sleep 1
done
ok "PostgreSQL is ready"

# Wait for Redis
log "Waiting for Redis to be ready..."
RETRIES=15
until docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; do
  RETRIES=$((RETRIES - 1))
  if [[ $RETRIES -le 0 ]]; then
    err "Redis did not become ready in time."
    exit 1
  fi
  sleep 1
done
ok "Redis is ready"

# Wait for n8n (only when the profile is active) — dependents (API callbacks,
# compile/push) need n8n's REST API reachable before they run.
if [[ -n "$COMPOSE_PROFILES" ]]; then
  log "Waiting for n8n to be ready..."
  RETRIES=60
  until curl -sf http://localhost:5678/healthz &>/dev/null; do
    RETRIES=$((RETRIES - 1))
    if [[ $RETRIES -le 0 ]]; then
      warn "n8n did not become ready in time — workflow execution will be unavailable."
      warn "Check: docker compose --profile n8n logs n8n"
      break
    fi
    sleep 1
  done
  if curl -sf http://localhost:5678/healthz &>/dev/null; then
    ok "n8n is ready on :5678 (editor: http://localhost:5678)"
  fi
fi

# ── 3. Check Ollama for embeddings ──
if command -v ollama &>/dev/null; then
  ok "Ollama found"
  # Ensure the embedding model is available
  if ! ollama list 2>/dev/null | grep -q 'nomic-embed-text'; then
    log "Pulling nomic-embed-text model (first time only)..."
    ollama pull nomic-embed-text
    ok "nomic-embed-text model ready"
  else
    ok "nomic-embed-text model available"
  fi
  # Make sure Ollama is serving
  if ! curl -sf http://localhost:11434/api/tags &>/dev/null; then
    warn "Ollama is installed but not serving — run 'ollama serve' in another terminal for embeddings"
  else
    ok "Ollama is serving on :11434"
  fi
else
  warn "Ollama not installed — embeddings/RAG will be unavailable"
  warn "Install: https://ollama.com  then run: ollama pull nomic-embed-text"
fi

# ── 4. Run database migrations ──
log "Running database migrations..."
cd apps/api
source .venv/bin/activate
if command -v alembic &>/dev/null && [[ -f alembic.ini ]]; then
  alembic upgrade head 2>&1 | tail -3
  ok "Migrations applied"
else
  warn "Alembic not found or no alembic.ini — skipping migrations"
fi
cd "$ROOT_DIR"

# ── 5. Install frontend dependencies (if needed) ──
if [[ ! -d "node_modules" ]]; then
  log "Installing Node.js dependencies..."
  npm install
  ok "Dependencies installed"
fi

# ── 6. Start FastAPI backend (background) ──
# Kill any stale process on port 8000
lsof -ti :8000 | xargs kill -9 2>/dev/null && warn "Killed stale process on :8000"
sleep 1

LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

log "Starting FastAPI backend on http://localhost:8000 ..."
cd apps/api
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000 > "$LOG_DIR/api.log" 2>&1 &
API_PID=$!
cd "$ROOT_DIR"

# Give the API a moment to start
sleep 2
if kill -0 "$API_PID" 2>/dev/null; then
  ok "API server running (PID $API_PID)"
else
  err "API server failed to start. Check the logs above."
  exit 1
fi

# ── 7. Start Celery worker (background) ──
log "Starting Celery worker..."
cd apps/api
source .venv/bin/activate
celery -A app.celery_app worker --loglevel=info -Q default,agents,orchestrator > "$LOG_DIR/celery.log" 2>&1 &
CELERY_PID=$!
cd "$ROOT_DIR"

sleep 2
if kill -0 "$CELERY_PID" 2>/dev/null; then
  ok "Celery worker running (PID $CELERY_PID)"
else
  warn "Celery worker failed to start — background tasks won't run. Check logs/celery.log"
  CELERY_PID=""
fi

# ── 8. Start Next.js frontend (background) ──
# Kill any stale process on port 3000
lsof -ti :3000 | xargs kill -9 2>/dev/null && warn "Killed stale process on :3000"
sleep 1
log "Starting Next.js frontend on http://localhost:3000 ..."
npm run dev > "$LOG_DIR/web.log" 2>&1 &
WEB_PID=$!

sleep 3
if kill -0 "$WEB_PID" 2>/dev/null; then
  ok "Web dev server running (PID $WEB_PID)"
else
  err "Web dev server failed to start."
  exit 1
fi

# ── Ready ──
echo ""
echo -e "${GREEN} Founder OS is running!${NC}"
echo -e "${GREEN} Web:  ${NC}http://localhost:3000  ${GREEN}║${NC}"
echo -e "${GREEN} API:  ${NC}http://localhost:8000  ${GREEN}║${NC}"
echo -e "${GREEN} Docs: ${NC}http://localhost:8000/docs ${GREEN}║${NC}"
if [[ -n "$COMPOSE_PROFILES" ]]; then
  echo -e "${GREEN} n8n:  ${NC}http://localhost:5678  ${GREEN}║${NC}"
fi

echo -e "${CYAN} Logs:${NC}"
echo -e "  API    → logs/api.log"
echo -e "  Web    → logs/web.log"
echo -e "  Celery → logs/celery.log"
if [[ -n "$COMPOSE_PROFILES" ]]; then
  echo -e "  n8n    → docker compose --profile n8n logs -f n8n"
fi
echo ""
echo -e "Tail logs:  ${YELLOW}tail -f logs/api.log logs/web.log logs/celery.log${NC}"
echo -e "Press ${YELLOW}Ctrl+C${NC} to stop all services."
echo ""

# Wait for background processes
wait
