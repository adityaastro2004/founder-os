# Founder OS

**An autonomous AI operating system that runs your startup.**

Founder OS is a multi-agent backend that acts as a tireless co-founder — it plans your week, writes your content, researches your market, monitors your operations, manages your product roadmap, and handles customer support. You talk to it; it talks to itself; work gets done.

Built for solo founders and tiny teams who need the output of a 10-person ops team but can't afford one.

---

## The Problem

Running a startup solo means you're the CEO, marketer, researcher, PM, support rep, and ops manager — all at once. You context-switch dozens of times a day. Important things fall through cracks. You spend more time *managing* work than *doing* work.

Existing AI tools help with isolated tasks (write a blog post, summarise a doc), but they don't understand your business holistically. They don't remember what you told them last week. They can't coordinate across domains. They're co-pilots — not co-founders.

## The Vision

Founder OS is not a chatbot. It's an **operating system** for your startup — a persistent, memory-rich, multi-agent system that:

- **Knows your business** — ingests your docs, metrics, integrations, and context into a vector knowledge base (pgvector) so every agent grounds its work in *your* reality
- **Plans and prioritises autonomously** — the Planner Agent breaks your goals into tasks, assigns them to specialist agents, and adjusts the plan as things change
- **Delegates internally** — agents talk to each other (Agent-to-Agent protocol) without you orchestrating every step. Ask for a product launch plan and the Planner coordinates Research, Content, Product, and Ops agents behind the scenes
- **Remembers everything** — 4-layer memory (conversation → working → shared → long-term RAG) means agents never lose context, across sessions or across agents
- **Uses your tools** — MCP (Model Context Protocol) lets agents connect to external tool servers (GitHub, Slack, Notion, Linear, analytics platforms) as first-class capabilities
- **Runs on your terms** — OSS-first, local-first. Default LLM is Ollama (free, runs on your machine). Swap to Anthropic or OpenAI when you need more power. No vendor lock-in.

The end state: you wake up, open Founder OS, and your AI team has already triaged support tickets, drafted this week's newsletter, flagged a competitor move, updated the roadmap, and prepared a prioritised task list for your day.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Founder OS                              │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Planner  │  │ Content  │  │ Research │  │   Ops    │       │
│  │  Agent   │←→│  Agent   │←→│  Agent   │←→│  Agent   │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
│       │              │              │              │             │
│  ┌────┴─────┐  ┌────┴─────┐                                    │
│  │ Product  │  │ Support  │   ... more agents over time         │
│  │  Agent   │  │  Agent   │                                     │
│  └────┬─────┘  └────┬─────┘                                    │
│       │              │                                          │
│  ─────┴──────────────┴──────────────────────────────────────    │
│  │  A2A Router  │  Event Bus (Redis)  │  Shared Memory  │      │
│  ───────────────────────────────────────────────────────────    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Execution Engine                       │   │
│  │  LLM call → tool calls (parallel) → loop → result       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ LLM Provider │  │ Tool Registry│  │   4-Layer Memory     │  │
│  │              │  │              │  │                      │  │
│  │ • Ollama     │  │ • Local tools│  │ • Conversation       │  │
│  │ • Anthropic  │  │ • MCP stdio  │  │ • Working (Redis)    │  │
│  │ • OpenAI-    │  │ • MCP SSE    │  │ • Shared (Redis)     │  │
│  │   compatible │  │              │  │ • Long-term (pgvec)  │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              PostgreSQL + pgvector                       │   │
│  │  24 tables · users · tasks · workflows · knowledge ·    │   │
│  │  metrics · integrations · analytics · audit logs        │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Core Design Principles

1. **No frameworks** — No LangChain, no CrewAI, no LlamaIndex. Every component (BaseAgent, ToolRegistry, Router, ExecutionEngine, Memory) is built from scratch. We use direct SDK calls and raw async Python. This means we understand every line, can debug anything, and aren't locked into someone else's abstractions.

2. **OSS-first** — Default LLM is Ollama running locally (free). PostgreSQL, Redis, FastAPI — all open source. You can run the entire system on a laptop with zero API costs.

3. **Backend-native** — This is a real backend system, not a notebook experiment. Async everywhere, proper database schema with migrations, JWT auth, structured API routes, Docker infrastructure.

4. **Composition over inheritance** — Agents are assembled from independent components (LLM + Tools + Memory + Router + EventBus) via the registry. Swap any piece without touching the others.

---

## What's Built

### Infrastructure
- **FastAPI** async API with lifespan management
- **PostgreSQL 16 + pgvector** — 24-table schema covering users, tasks, workflows, knowledge base, business metrics, integrations, agent analytics, audit logs, notifications, and billing
- **Redis 7** — caching, working memory, shared memory, pub/sub event bus
- **Alembic** migrations
- **Clerk JWT auth** (RS256 / JWKS verification)
- **Docker Compose** for Postgres + Redis

### Agent System
- **BaseAgent** — composable agent core with system prompts, tool use loops, memory, delegation, and event emission
- **6 Specialist Agents** — Planner, Content, Research, Ops, Product, Support — each with distinct capabilities, tools, and system prompts
- **LLM Provider abstraction** — Ollama (free/local), Anthropic (Claude), OpenAI-compatible (vLLM, Together, Groq, LM Studio) — all via direct SDK/HTTP, hot-swappable via config
- **Tool Protocol (MCP-compatible)** — `ToolProvider` interface, `LocalToolProvider` for built-in tools, `ToolRegistry` for multi-provider aggregation, parallel tool execution
- **MCP Adapter** — stdio and SSE transport clients for connecting to external MCP tool servers (JSON-RPC 2.0)
- **A2A Router** — Agent-to-Agent capability-based routing and delegation. Agents declare capabilities via `AgentCard`; the router scores and dispatches tasks to the best-fit agent
- **Execution Engine** — step-based agentic loop with parallel tool calls, cost tracking, token accounting, and configurable max rounds
- **Event Bus** — Redis pub/sub for async inter-agent communication (agent.started, task.created, delegation.requested, etc.)
- **4-Layer Memory** —
  - *Conversation*: in-process rolling window (50 messages)
  - *Working*: Redis-backed, per-agent, per-session, 4hr TTL
  - *Shared*: Redis-backed, cross-agent scratch-pad, 8hr TTL
  - *Long-term*: pgvector cosine similarity RAG over the knowledge base
- **11 Built-in Tools** — search_knowledge, web_search, get_business_metrics, create_task, list_tasks, update_task_status, save_draft, get_integrations, get_writing_style, get_current_datetime, store_working_memory

### API
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check (API + Postgres + Redis) |
| `GET` | `/api/agents/` | List available agents |
| `GET` | `/api/agents/system` | Agent system config info |
| `POST` | `/api/agents/{name}/run` | Send a message to an agent |

---

## Where It's Going

### Near-term

- [ ] **Embedding pipeline** — auto-generate vector embeddings on knowledge ingestion (Ollama `nomic-embed-text` / OpenAI `text-embedding-3-small`) so RAG activates at query time
- [ ] **MCP server connections** — wire MCP adapter into config so agents can connect to GitHub, Slack, Linear, Notion tool servers out of the box
- [ ] **Workflow engine** — multi-step, multi-agent workflow execution (the schema and models are ready; the orchestration logic is next)
- [ ] **Real tool implementations** — replace placeholder tools with actual DB queries, API calls, and integrations
- [ ] **Streaming responses** — SSE streaming from agents to the frontend
- [ ] **Background agent runs** — async task queue (Redis + background workers) for long-running agent workflows

### Mid-term

- [ ] **Web dashboard** (Next.js `web` app) — chat interface, task boards, knowledge base management, agent configuration, metrics dashboards
- [ ] **Integration connectors** — Stripe, GitHub, Slack, Notion, Linear, Google Analytics, Twitter/X, email (IMAP/SMTP)
- [ ] **Scheduled agents** — cron-like triggers ("every Monday, Planner creates the weekly plan; every morning, Ops runs the daily standup")
- [ ] **Learning loop** — agents improve from feedback; `TaskFeedback` and `LearningInsight` tables are ready
- [ ] **Multi-user / team support** — role-based access, shared workspaces

### Long-term Vision

- [ ] **Autonomous workflows** — agents trigger each other without human input. A support ticket comes in → Support Agent drafts a response → Product Agent logs a bug → Ops Agent updates the sprint
- [ ] **Voice interface** — talk to Founder OS like a co-founder
- [ ] **Mobile app** — founder OS in your pocket, push notifications for critical alerts
- [ ] **Marketplace** — community-built agents, tools, and workflow templates
- [ ] **Self-improving system** — agents analyse their own performance, identify failure modes, and suggest prompt/tool improvements

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI (Python 3.14, async) |
| Database | PostgreSQL 16 + pgvector |
| Cache / Memory / Events | Redis 7 |
| Auth | Clerk (JWT / JWKS) |
| LLM (default) | Ollama (local, free) |
| LLM (optional) | Anthropic Claude, OpenAI-compatible APIs |
| Migrations | Alembic |
| Frontend | Next.js (Turborepo monorepo) |
| Infrastructure | Docker Compose |

## Project Structure

```
founder-os/
├── apps/
│   ├── api/                    # Python backend (FastAPI)
│   │   ├── app/
│   │   │   ├── main.py         # FastAPI app + lifespan
│   │   │   ├── config.py       # Settings (pydantic-settings)
│   │   │   ├── database.py     # Async SQLAlchemy engine
│   │   │   ├── redis.py        # Async Redis client
│   │   │   ├── auth.py         # Clerk JWT verification
│   │   │   ├── models.py       # 24-table ORM (pgvector)
│   │   │   ├── api/
│   │   │   │   ├── routes.py   # Health + general routes
│   │   │   │   └── agent_routes.py  # Agent API endpoints
│   │   │   └── agents/
│   │   │       ├── base.py          # BaseAgent (core)
│   │   │       ├── agents.py        # 6 specialist agents
│   │   │       ├── llm.py           # LLM provider abstraction
│   │   │       ├── tool_protocol.py # MCP-compatible tool registry
│   │   │       ├── mcp_adapter.py   # MCP stdio/SSE clients
│   │   │       ├── tools.py         # @tool decorator + catalog
│   │   │       ├── builtin_tools.py # 11 built-in tools
│   │   │       ├── memory.py        # 4-layer memory system
│   │   │       ├── router.py        # A2A agent router
│   │   │       ├── execution.py     # Step-based execution engine
│   │   │       ├── event_bus.py     # Redis pub/sub event bus
│   │   │       ├── registry.py      # Agent factory + composition
│   │   │       └── config.py        # Agent-specific config
│   │   ├── schema.sql               # Full DDL (24 tables)
│   │   ├── alembic/                 # DB migrations
│   │   └── requirements.txt
│   ├── web/                    # Next.js frontend (dashboard)
│   └── docs/                   # Next.js docs site
├── packages/
│   ├── ui/                     # Shared React components
│   ├── eslint-config/          # Shared ESLint config
│   └── typescript-config/      # Shared TS config
├── docker-compose.yml
└── turbo.json
```

## Quick Start

```bash
# 1. Start infrastructure
docker compose up -d   # PostgreSQL + Redis

# 2. Set up the API
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env   # Edit with your settings
# Default LLM is Ollama — install it: https://ollama.com
ollama pull llama3.1:8b

# 4. Run migrations
alembic upgrade head

# 5. Start the server
uvicorn app.main:app --reload --port 8000

# 6. Check health
curl http://localhost:8000/api/health
```

---

## Philosophy

> "The best startup tool is one that does the work, not one that helps you do the work."

Founder OS exists because we believe AI agents should be **systems**, not **features**. Not a chat widget bolted onto a dashboard — a persistent, intelligent backend that operates your business around the clock.

Every design decision flows from one question: *what would a tireless, infinitely patient, always-available co-founder do?*

---

## License

MIT
