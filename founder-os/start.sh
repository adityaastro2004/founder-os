#!/bin/bash
# start.sh - Start the complete Founder OS stack
# Usage: ./start.sh          (start everything)
#        ./start.sh --stop   (stop everything)

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

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
  [[ -n "$API_PID" ]] && kill "$API_PID" 2>/dev/null && ok "API server stopped"
  [[ -n "$WEB_PID" ]] && kill "$WEB_PID" 2>/dev/null && ok "Web dev server stopped"
  docker compose down 2>/dev/null && ok "Docker services stopped"
  exit 0
}

# ── Stop mode ──
if [[ "$1" == "--stop" ]]; then
  log "Stopping all services..."
  # Kill any running uvicorn on port 8000
  lsof -ti :8000 | xargs kill -9 2>/dev/null && ok "API server stopped" || warn "No API server found on :8000"
  # Kill any running next dev on port 3000
  lsof -ti :3000 | xargs kill -9 2>/dev/null && ok "Web dev server stopped" || warn "No web server found on :3000"
  docker compose down 2>/dev/null && ok "Docker services stopped" || warn "Docker services not running"
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

# ── 2. Start Docker services (PostgreSQL + Redis) ──
log "Starting PostgreSQL & Redis..."
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

# ── 3. Run database migrations ──
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

# ── 4. Install frontend dependencies (if needed) ──
if [[ ! -d "node_modules" ]]; then
  log "Installing Node.js dependencies..."
  npm install
  ok "Dependencies installed"
fi

# ── 5. Start FastAPI backend (background) ──
# Kill any stale process on port 8000
lsof -ti :8000 | xargs kill -9 2>/dev/null && warn "Killed stale process on :8000"
sleep 1
log "Starting FastAPI backend on http://localhost:8000 ..."
cd apps/api
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000 &
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

# ── 6. Start Next.js frontend (background) ──
# Kill any stale process on port 3000
lsof -ti :3000 | xargs kill -9 2>/dev/null && warn "Killed stale process on :3000"
sleep 1
log "Starting Next.js frontend on http://localhost:3000 ..."
npm run dev &
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

echo ""
echo -e "Press ${YELLOW}Ctrl+C${NC} to stop all services."
echo ""

# Wait for background processes
wait
