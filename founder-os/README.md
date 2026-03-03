# Founder OS — Monorepo

This is the Turborepo monorepo for **Founder OS**, an autonomous AI operating system for startups. See the [project README](../readme.md) for the full vision, architecture, and roadmap.

## Apps

| App | Stack | Description |
|-----|-------|-------------|
| `apps/api` | FastAPI + Python 3.14 | Multi-agent AI backend — 64+ endpoints, 7 agents, 28 DB tables, Celery queue, APScheduler, Google Calendar MCP |
| `apps/web` | Next.js 16 + Tailwind v4 | Dashboard frontend — 8 pages, Clerk auth, SSE streaming, responsive design |
| `apps/docs` | Next.js | Documentation site (WIP) |

## Packages

| Package | Description |
|---------|-------------|
| `packages/ui` | Shared React component library |
| `packages/eslint-config` | Shared ESLint configuration |
| `packages/typescript-config` | Shared TypeScript configuration |

## Frontend (`apps/web`)

### Tech Stack
- **Next.js 16** with App Router
- **Tailwind CSS v4** with CSS design tokens
- **Clerk** for authentication (sign-in, sign-up, user management)
- **SSE (Server-Sent Events)** for real-time agent activity feed
- **Streaming fetch** for chat responses

### Dashboard Pages

| Page | Route | Features |
|------|-------|----------|
| **Dashboard** | `/dashboard` | Stats overview, quick actions, real-time activity feed, agent status cards |
| **Chat** | `/dashboard/chat` | Conversational agent interface with SSE streaming, tool call visualization, auto-delegation |
| **Agents** | `/dashboard/agents` | Real-time agent status, SSE event feed, run agent modal, stats bar |
| **Planner** | `/dashboard/planner` | Google Calendar integration, MCP tools panel, AI plan generation, plan history |
| **Tasks** | `/dashboard/tasks` | Task review workflow (approve/reject/edit/feedback), split-panel view, star ratings |
| **Knowledge** | `/dashboard/knowledge` | Knowledge base CRUD, text/URL ingestion, semantic search |
| **Memory** | `/dashboard/memory` | Long-term memory management, chapter filtering, pin/delete, store new memories |
| **Settings** | `/dashboard/settings` | Clerk UserProfile integration |

### Key Frontend Features
- **Stable API hook** (`useApi`) — `useCallback`-wrapped with ref-based token access, prevents re-render loops
- **SSE hook** (`useEventSource`) — Clerk auth, exponential backoff reconnect (max 10 attempts), ref-stabilized token
- **Streaming fetch** (`useStreamingFetch`) — POST-based SSE for chat, auto-abort on unmount
- **4-step onboarding wizard** — Business info, goals, metrics, preferences
- **Responsive design** — Mobile-first grids, `100dvh` viewport, adaptive layouts
- **Dark mode** — Via `prefers-color-scheme` with CSS variables
- **Error handling** — Try/catch on all API actions, user-friendly error messages, retry logic
- **Delete confirmations** — Knowledge and memory items require confirmation before deletion

## Backend (`apps/api`)

### Tech Stack
- **FastAPI** with async endpoints
- **PostgreSQL 16 + pgvector** — 28 tables, 3 views, 30+ indexes
- **Redis 7** — Pub/sub for EventBus, agent state caching, 4-layer memory
- **Celery** — Background task queue for long-running orchestrations
- **APScheduler** — Weekly plan auto-generation (Monday mornings)
- **Clerk** — JWT auth validation via `require_auth` dependency

### Agent System
- **7 specialist agents**: Orchestrator, Planner, Content, Research, Ops, Product, Support
- **Orchestrator** — Stripe Minions-inspired: Analyse → Plan → Delegate → Synthesise
- **20+ tools per agent** including intent detection (`detect_calendar_intent`, `validate_event_fields`)
- **3-tier LLM fallback**: Gemini 2.5 Flash → gpt-4o-mini → Ollama
- **Approval Gate** — 3-tier risk classification (LOW/MEDIUM/HIGH)
- **A2A protocol** — Agent-to-agent delegation without user routing

### MCP (Model Context Protocol) Tools
8 Google Calendar MCP tools:
- `list_upcoming_events` — with description, ai_generated flag, creator_email
- `create_event`, `create_all_day_event`, `update_event`, `delete_event`, `get_event`
- `push_weekly_plan` — bulk push from AI planner
- `gcal_smart_delete` — bulk delete AI-generated events

### Real-time System
- **EventBus** — Redis pub/sub for SSE event streaming
- **SSE endpoints**: `/api/activity/stream`, `/api/agents/orchestrate/stream`
- **Tool event emission** — Every tool call/result emitted to the event bus

## Quick Start

### Prerequisites
- Node.js 18+, pnpm
- Python 3.14+, pip
- Docker (for PostgreSQL + Redis)
- Clerk account (for auth)

### Setup

```bash
# 1. Clone and install frontend dependencies
pnpm install

# 2. Start infrastructure
docker compose up -d   # PostgreSQL + Redis

# 3. Set up Python environment
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Run database migrations
alembic upgrade head

# 5. Start API server
uvicorn app.main:app --reload --port 8000

# 6. Start frontend (separate terminal)
cd ../..
turbo dev --filter=web
```

### Environment Variables

#### Frontend (`apps/web/.env.local`)
```
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_...
CLERK_SECRET_KEY=sk_...
NEXT_PUBLIC_API_URL=http://localhost:8000
```

#### Backend (`apps/api/.env`)
```
DATABASE_URL=postgresql://...
REDIS_URL=redis://localhost:6379
CLERK_SECRET_KEY=sk_...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GEMINI_API_KEY=...
OPENAI_API_KEY=...  # optional fallback
```

## Development Commands

```bash
# Frontend dev (hot reload)
turbo dev --filter=web

# Build all apps
turbo build

# API server with auto-reload
cd apps/api && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000

# Celery worker (background tasks)
cd apps/api && source .venv/bin/activate && celery -A app.celery_app worker --loglevel=info -Q default,agents,orchestrator

# Build specific app
turbo build --filter=docs
```
