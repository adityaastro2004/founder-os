# Founder OS

**An autonomous AI operating system that runs your startup.**

Founder OS is a multi-agent backend that acts as a tireless co-founder — it plans your week, writes your content, researches your market, monitors your operations, manages your product roadmap, and handles customer support. You talk to it; it talks to itself; work gets done.

No workflow builders. No drag-and-drop. No manual automation setup. Founder OS **automatically generates and evolves custom workflows** tailored to your company — and scales them as you grow.

Built for solo founders and tiny teams who need the output of a 10-person ops team but can't afford one.

---

## The Problem

Running a startup solo means you're the CEO, marketer, researcher, PM, support rep, and ops manager — all at once. You context-switch dozens of times a day. Important things fall through cracks. You spend more time *managing* work than *doing* work.

Existing AI tools help with isolated tasks (write a blog post, summarise a doc), but they don't understand your business holistically. They don't remember what you told them last week. They can't coordinate across domains. They're co-pilots — not co-founders.

And workflow tools like n8n, Zapier, or Make? They require *you* to design every automation by hand. You have to know what to automate, wire up every trigger and step, and rebuild flows as your company changes. That's more busywork, not less.

## The Vision

Founder OS is not a chatbot. It's an **operating system** for your startup — a persistent, memory-rich, multi-agent system that:

- **Knows your business** — ingests your docs, metrics, integrations, and context into a vector knowledge base (pgvector) so every agent grounds its work in *your* reality
- **One entry point, zero routing** — you talk to the **Orchestrator** (inspired by [Stripe's Minions](https://arxiv.org/abs/2402.15678)). It analyses your request, decomposes it into subtasks, delegates to the right specialist agents, and synthesises one coherent answer. You never pick an agent.
- **Auto-generated workflows** — no drag-and-drop, no manual automation. The Orchestrator creates **custom multi-agent workflows on the fly** based on what your company actually needs. As your startup grows — new integrations, more data, bigger team — workflows evolve automatically. What n8n/Zapier/Make require you to build by hand, Founder OS figures out and runs for you.
- **Delegates internally** — agents talk to each other (Agent-to-Agent protocol) without you orchestrating every step. Ask for a product launch plan and the Orchestrator coordinates Research, Content, Product, and Ops agents behind the scenes
- **Remembers everything** — 4-layer agent memory + temporal knowledge graph with composite scoring, spaced-repetition review, entity linking, and typed relationships
- **Plans your week** — automated weekly planner with Google Calendar integration, ICE-scored priorities, and Monday-morning auto-generation via APScheduler
- **Human-in-the-loop** — approval system with 3-tier risk classification (LOW / MEDIUM / HIGH), per-user preferences, and mandatory gating for irreversible actions
- **Uses your tools** — MCP (Model Context Protocol) lets agents connect to external tool servers (GitHub, Slack, Notion, Linear, analytics platforms) as first-class capabilities
- **Runs in the background** — Celery task queue for long-running orchestrations with status polling, cancellation, and per-user task history
- **Scales with you** — Day 1 you're a solo founder and the system runs simple single-agent tasks. Month 6 you have a team, 10 integrations, and complex cross-functional processes — the same system handles it, automatically composing more sophisticated agent workflows as your context grows
- **Runs on your terms** — OSS-first, local-first. Default LLM is Ollama (free, runs on your machine). Swap to Anthropic, Gemini, or any OpenAI-compatible API when you need more power. No vendor lock-in.

The end state: you wake up, open Founder OS, and your AI team has already triaged support tickets, drafted this week's newsletter, flagged a competitor move, updated the roadmap, and prepared a prioritised task list for your day. No workflow was manually configured — the system figured out what to do based on your goals, data, and history.

---

## Architecture

```
                        ┌──────────────────┐
                        │   User Message   │
                        └────────┬─────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Founder OS                              │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              ORCHESTRATOR (Stripe Minions)               │   │
│  │                                                         │   │
│  │  Analyse → Plan → Delegate → Synthesise                 │   │
│  │  Agents-as-tools: the LLM decides the workflow          │   │
│  └───┬──────────┬──────────┬──────────┬──────────┬────────┘   │
│      ▼          ▼          ▼          ▼          ▼             │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐      │
│  │Planner │ │Content │ │Research│ │  Ops   │ │Product │      │
│  │ Agent  │ │ Agent  │ │ Agent  │ │ Agent  │ │ Agent  │      │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘      │
│                              ┌────────┐                       │
│                              │Support │  ... + custom agents  │
│                              │ Agent  │                       │
│                              └────────┘                       │
│                                                                 │
│  ─────────────────────────────────────────────────────────────  │
│  │ Approval Gate │ A2A Router │ Event Bus │ Shared Memory   │  │
│  ─────────────────────────────────────────────────────────────  │
│                                                                 │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐   │
│  │ Execution Eng  │  │ Celery Queue   │  │ APScheduler    │   │
│  │ LLM→tools→loop │  │ async bg tasks │  │ weekly planner │   │
│  └────────────────┘  └────────────────┘  └────────────────┘   │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ LLM Provider │  │ Tool Registry│  │   Memory System      │  │
│  │              │  │              │  │                      │  │
│  │ • Ollama     │  │ • Local tools│  │  4-Layer Agent Mem   │  │
│  │ • Anthropic  │  │ • MCP stdio  │  │ • Conversation       │  │
│  │ • Gemini     │  │ • MCP SSE    │  │ • Working (Redis)    │  │
│  │ • OpenAI-    │  │ • Closures   │  │ • Shared (Redis)     │  │
│  │   compatible │  │              │  │ • Long-term (pgvec)  │  │
│  │              │  │              │  │                      │  │
│  │ 3-tier       │  │              │  │  Temporal Knowledge  │  │
│  │ fallback     │  │              │  │  Graph (memory_pages │  │
│  │              │  │              │  │  + memory_links)     │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  PostgreSQL 16 + pgvector · Redis 7 · Google Calendar   │   │
│  │  28 tables · 3 views · 30+ indexes · 4 seed workflows   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### How Auto-Workflows Work (vs. n8n / Zapier / Make)

Traditional workflow tools require you to **design every automation by hand**:

| | n8n / Zapier / Make | Founder OS |
|---|---|---|
| Workflow creation | Manual drag-and-drop | **Auto-generated by the Orchestrator** |
| Knows your business | No | Yes — pgvector knowledge base + metrics + history |
| Adapts as you grow | You rebuild flows | **Workflows evolve automatically** |
| Cross-domain coordination | You wire each connection | **Agents coordinate via A2A protocol** |
| Requires expertise | Yes — you design the logic | **Just describe what you need** |

When you say *"prepare for our Series A"*, the Orchestrator doesn't look up a pre-built workflow. It **creates one on the fly**:

1. Delegates to **Research Agent** → competitor landscape, market sizing
2. Delegates to **Product Agent** → traction metrics, roadmap summary
3. Delegates to **Content Agent** → pitch deck narrative, investor FAQ
4. Delegates to **Ops Agent** → due diligence checklist, data room prep
5. **Synthesises** everything into a cohesive action plan

Next month, when you say the same thing, the workflow will be **different** — because your metrics changed, you have new integrations, and the agents have learned from your feedback. No manual rewiring needed.

### Core Design Principles

1. **No frameworks** — No LangChain, no CrewAI, no LlamaIndex. Every component (BaseAgent, ToolRegistry, Router, ExecutionEngine, Memory) is built from scratch. We use direct SDK calls and raw async Python. This means we understand every line, can debug anything, and aren't locked into someone else's abstractions.

2. **OSS-first** — Default LLM is Ollama running locally (free). PostgreSQL, Redis, FastAPI — all open source. You can run the entire system on a laptop with zero API costs.

3. **Backend-native** — This is a real backend system, not a notebook experiment. Async everywhere, proper database schema with migrations, JWT auth, structured API routes, Docker infrastructure.

4. **Composition over inheritance** — Agents are assembled from independent components (LLM + Tools + Memory + Router + EventBus) via the registry. Swap any piece without touching the others.

---

## What's Built

### Infrastructure
- **FastAPI** async API with lifespan management — **64 endpoints** across 9 route groups
- **PostgreSQL 16 + pgvector** — 24-table core schema + 4 planner/memory tables (28 total), 3 views, 30+ indexes, seed data for agents, workflows, and subscription plans
- **Redis 7** — caching, working memory, shared memory, pub/sub event bus, approval queue, Celery broker
- **Alembic** migrations
- **Clerk JWT auth** (RS256 / JWKS verification)
- **Docker Compose** — PostgreSQL (pgvector/pgvector:pg16) + Redis (redis:7-alpine) with health checks and named volumes
- **Celery task queue** — Redis-backed async worker with 3 queues (default, agents, orchestrator), 5-minute soft timeout, auto-retry, JSON serialization
- **APScheduler** — cron-based background scheduler for automated weekly plan generation (Monday 08:00 IST)

### Agent System
- **Orchestrator** — top-level manager agent (Stripe Minions pattern). Analyses any request, decomposes into subtasks, delegates to specialists via `delegate_task` tool, synthesises the response. The LLM decides the workflow — no hardcoded routing
- **BaseAgent** — composable agent core with system prompts, tool use loops, memory, delegation, and event emission
- **7 Agents** — Orchestrator + 6 Specialists (Planner, Content, Research, Ops, Product, Support) — each with distinct capabilities, tools, and system prompts
- **Agents-as-tools** — specialist agents are exposed to the Orchestrator as callable tools. The `delegate_task` tool is bound at runtime via closure injection — the Orchestrator's LLM sees it as a regular tool, but it spawns a full agent under the hood
- **LLM Provider abstraction** — 6 provider classes, 4 selectable via factory:
  - *Ollama* — free/local, no API key required
  - *Anthropic* — Claude (official SDK, full tool-use support)
  - *OpenAI-compatible* — vLLM, Together AI, Groq, LM Studio, LocalAI
  - *Gemini* — OpenAI-compatible endpoint + native REST API + **3-tier fallback** (Gemini OpenAI-compat → Gemini Native REST → OpenAI) for maximum reliability
- **Tool Protocol (MCP-compatible)** — `ToolProvider` interface, `LocalToolProvider` for built-in tools, `ToolRegistry` for multi-provider aggregation, parallel tool execution, runtime closure overrides
- **MCP Adapter** — stdio and SSE transport clients for connecting to external MCP tool servers (JSON-RPC 2.0)
- **A2A Router** — Agent-to-Agent capability-based routing and delegation. Agents declare capabilities via `AgentCard`; the router scores and dispatches tasks to the best-fit agent
- **Execution Engine** — step-based agentic loop with parallel tool calls, cost tracking, token accounting, and configurable max rounds
- **Event Bus** — Redis pub/sub for async inter-agent communication (agent.started, orchestration.started, delegation.requested, etc.)
- **12 Built-in Tools** — delegate_task, search_knowledge, web_search, get_business_metrics, create_task, list_tasks, update_task_status, save_draft, get_integrations, get_writing_style, get_current_datetime, store_working_memory

### Memory System (Dual Architecture)

**4-Layer Agent Memory** — composed via `AgentMemory`, assembled into context at runtime:

| Layer | Backend | Scope | TTL |
|-------|---------|-------|-----|
| Conversation | In-process (list) | Single agent run | Session (rolling 50 messages) |
| Working | Redis | Per-user, per-agent, per-session | 4 hours |
| Shared | Redis | Cross-agent scratch-pad | 8 hours |
| Long-term | PostgreSQL + pgvector | Per-user, permanent | ∞ (cosine similarity, min 0.70) |

**Temporal Knowledge Graph** — a second memory system (`memory_pages` + `memory_links`) with:
- **Composite scoring**: `(semantic_sim × w₁) + (temporal_relevance × w₂) + (importance × w₃) + (access_freq × w₄)`
- **Spaced-repetition review** — memories are surfaced for review on schedule, strengthening recall
- **Entity extraction** — memories tagged with entities (people, companies, tools) for entity-based search
- **Chapters** — memories are organized into named chapters for browsable context
- **Typed links** — relationships between memories: `related`, `caused_by`, `led_to`, `contradicts`, `updates`, `supersedes`, `part_of` (with strength 0–1)
- **Decay + pinning** — unpinned memories decay over time; pinned memories persist indefinitely

### Approval System (Human-in-the-Loop)

Every tool call flows through `ApprovalGate` before execution:

| Risk Level | Behavior | Examples |
|------------|----------|----------|
| **LOW** | Auto-approved by default | search, list, get operations |
| **MEDIUM** | Follows user preference | create_task, save_draft |
| **HIGH** | **Always requires explicit approval** — cannot be bypassed | git push, post tweet, send email, deploy, payments (30 high-risk tools mapped) |

Per-user preferences stored in Redis: `always_allow` / `always_deny` / `ask`. HIGH-risk tools cannot be set to `always_allow`. Pending approvals expire after 1 hour.

### Weekly Planner

Full weekly planning pipeline with Google Calendar integration:

- **Onboarding** — business profile intake (name, type, stage, industry, goals, team size)
- **Plan generation** — LLM-powered structured weekly plans with ICE scoring (Impact × Confidence × Ease), daily schedules, task assignments, delegations, risks, and success criteria
- **Google Calendar sync** — OAuth2 flow, token management, push plans as calendar events, CRUD individual events
- **ICS export** — download plans as `.ics` files
- **Automated scheduling** — APScheduler cron job generates plans every Monday at 08:00 AM IST for all connected users
- **Plan history** — all past plans stored with stats (task count, events created, duration)
- **Smart prompt endpoint** — natural language interface that understands intent, pulls memory, creates events, updates context, and/or replans the week

### Knowledge Base

Full knowledge ingestion and retrieval system:

- **Ingest** — plain text, URLs, structured JSON, or batch (up to 50 documents)
- **Search** — hybrid/semantic/fulltext search across the knowledge base
- **CRUD** — list, get, delete individual items or bulk delete by category
- **Stats** — knowledge base statistics including embedding coverage

### Background Queue

Celery-powered async execution:

- **Submit** — queue agent runs or orchestrations for background execution
- **Poll** — check task status and retrieve results
- **History** — list recent background tasks per user
- **Cancel** — cancel pending or running tasks
- **Config** — 3 dedicated queues, 5-min soft limit, 6-min hard kill, auto-retry with exponential backoff

### API (64 Endpoints)

#### Core
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | API running check |
| `GET` | `/api/health` | Health check (API + Postgres + Redis) |
| `GET` | `/api/me` | Authenticated user identity |
| `GET` | `/api/greet` | Public greeting (optional auth) |

#### Agents
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/agents/orchestrate` | **Primary entry point** — send any message, Orchestrator handles everything |
| `GET` | `/api/agents/` | List available agents |
| `GET` | `/api/agents/system` | Agent system config (LLM provider, model, registered agents, event bus status) |
| `POST` | `/api/agents/{name}/run` | Send a message directly to a specific agent |

#### Approvals
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/approvals/pending` | List pending approvals |
| `POST` | `/api/approvals/{id}/approve` | Approve a pending action |
| `POST` | `/api/approvals/{id}/reject` | Reject a pending action |
| `GET` | `/api/approvals/preferences` | Get approval preferences |
| `POST` | `/api/approvals/preferences` | Set tool preference (always_allow / always_deny / ask) |
| `DELETE` | `/api/approvals/preferences/{tool}` | Clear a tool preference |
| `GET` | `/api/approvals/risk-info` | Risk classification for all tools |

#### Background Queue
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/queue/agents/{name}/run` | Submit agent run to background queue |
| `POST` | `/api/queue/orchestrate` | Submit orchestration to background queue |
| `GET` | `/api/queue/tasks/{id}` | Poll background task status/result |
| `GET` | `/api/queue/tasks` | List user's recent background tasks |
| `POST` | `/api/queue/tasks/{id}/cancel` | Cancel a background task |

#### Knowledge Base
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/knowledge/ingest/text` | Ingest plain text |
| `POST` | `/api/knowledge/ingest/url` | Ingest from URL |
| `POST` | `/api/knowledge/ingest/json` | Ingest structured JSON |
| `POST` | `/api/knowledge/ingest/batch` | Batch ingest (max 50) |
| `POST` | `/api/knowledge/search` | Search knowledge base |
| `GET` | `/api/knowledge/stats` | Knowledge base statistics |
| `GET` | `/api/knowledge/items` | List knowledge items |
| `GET` | `/api/knowledge/items/{id}` | Get single item |
| `DELETE` | `/api/knowledge/items/{id}` | Delete single item |
| `DELETE` | `/api/knowledge/items` | Bulk delete (optionally by category) |

#### Weekly Planner
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/planner/onboard` | Business profile onboarding |
| `GET` | `/api/planner/connect` | Start Google Calendar OAuth2 flow |
| `GET` | `/api/planner/connect/callback` | OAuth2 callback |
| `POST` | `/api/planner/update` | Update business context |
| `POST` | `/api/planner/generate` | Force immediate plan generation + GCal push |
| `GET` | `/api/planner/status` | Planner status (connection, last plan, goals) |
| `GET` | `/api/planner/history` | Past plan summaries |
| `POST` | `/api/planner/prompt` | **Smart NL endpoint** — send any prompt, system plans accordingly |
| `GET` | `/api/planner/calendar` | View upcoming calendar events |
| `GET` | `/api/planner/calendar/event/{id}` | Get single event |
| `POST` | `/api/planner/calendar/event` | Create calendar event directly |
| `PATCH` | `/api/planner/calendar/event/{id}` | Update calendar event |
| `DELETE` | `/api/planner/calendar/event/{id}` | Delete calendar event |

#### Memory (Temporal Knowledge Graph)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/memory/store` | Store a memory page |
| `POST` | `/api/memory/recall` | Recall memories (composite scoring) |
| `GET` | `/api/memory/reviews` | Memories due for spaced-repetition review |
| `POST` | `/api/memory/review/{id}` | Mark memory as reviewed |
| `GET` | `/api/memory/chapters` | List memory chapters |
| `GET` | `/api/memory/chapter/{chapter}` | Browse chapter memories |
| `POST` | `/api/memory/search/entity` | Entity-based memory search |
| `POST` | `/api/memory/link` | Create typed link between memories |
| `GET` | `/api/memory/links/{id}` | Get linked memories |
| `GET` | `/api/memory/stats` | Memory system statistics |
| `POST` | `/api/memory/pin/{id}` | Pin/unpin a memory |
| `DELETE` | `/api/memory/{id}` | Soft-delete a memory |

#### Test / Dev (dev-only)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/test/chat` | Direct LLM chat (no auth) |
| `GET` | `/api/test/provider` | LLM provider health check |
| `POST` | `/api/test/weekly-context` | Set test business context |
| `GET` | `/api/test/weekly-context` | Get current context |
| `DELETE` | `/api/test/weekly-context` | Reset to mock data |
| `POST` | `/api/test/plan` | Generate test plan |
| `GET` | `/api/test/plan/ical` | Download plan as .ics |
| `GET` | `/api/test/plan/gcal/auth` | Google Calendar OAuth (dev) |
| `GET` | `/api/test/plan/gcal/callback` | OAuth callback (dev) |
| `POST` | `/api/test/plan/gcal/push` | Push plan to Google Calendar (dev) |

---

## Where It's Going

### Near-term

- [ ] **Embedding pipeline** — auto-generate vector embeddings on knowledge ingestion (Ollama `nomic-embed-text` / OpenAI `text-embedding-3-small`) so RAG activates at query time (knowledge ingestion and search endpoints are built; embedding generation needs wiring)
- [ ] **MCP server connections** — wire MCP adapter into config so agents can connect to GitHub, Slack, Linear, Notion tool servers out of the box (adapter is built; config-driven connection layer needed)
- [ ] **Workflow persistence** — save orchestrator-generated workflows as reusable templates; the system learns which patterns work for your company and reuses them
- [ ] **Real tool implementations** — replace placeholder/mock tools with actual DB queries, API calls, and integrations (knowledge search and task tools are wired; web_search, metrics, integrations still use mock data)
- [ ] **Streaming responses** — SSE streaming from agents to the frontend

### Mid-term

- [ ] **Web dashboard** (Next.js `web` app) — chat interface, task boards, knowledge base management, agent configuration, metrics dashboards
- [ ] **Integration connectors** — Stripe, GitHub, Slack, Notion, Linear, Google Analytics, Twitter/X, email (IMAP/SMTP) (Google Calendar is fully integrated)
- [ ] **Scheduled orchestrations** — configurable cron triggers beyond the Monday weekly plan ("every morning, Ops standup + metrics check") (APScheduler is in place; needs UI-driven schedule management)
- [ ] **Workflow evolution** — as new integrations and data sources connect, the orchestrator automatically incorporates them into workflows without reconfiguration
- [ ] **Learning loop** — agents improve from feedback; `TaskFeedback` and `LearningInsight` tables are ready. Workflows that produce good results get reinforced; poor ones get adapted
- [ ] **Multi-user / team support** — role-based access, shared workspaces, per-team agent configurations

### Long-term Vision

- [ ] **Fully autonomous operations** — agents trigger each other without human input. A support ticket → Support Agent responds → Product Agent logs a bug → Ops Agent updates the sprint → Content Agent drafts a changelog. All auto-orchestrated.
- [ ] **Company-aware workflow generation** — the system uses your business stage (pre-seed, seed, Series A, growth), team size, industry, and integrations to generate completely different workflow strategies. A 2-person SaaS startup gets different automation than a 20-person e-commerce company.
- [ ] **Voice interface** — talk to Founder OS like a co-founder
- [ ] **Mobile app** — Founder OS in your pocket, push notifications for critical alerts
- [ ] **Marketplace** — community-built agents, tools, and workflow templates
- [ ] **Self-improving system** — agents analyse their own performance, identify failure modes, and refine prompts + workflows automatically

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI (Python 3.14, async) |
| Database | PostgreSQL 16 + pgvector (28 tables) |
| Cache / Memory / Events | Redis 7 |
| Auth | Clerk (JWT / JWKS) |
| Task Queue | Celery (Redis broker, 3 queues) |
| Scheduler | APScheduler (cron-based) |
| LLM (default) | Ollama (local, free) |
| LLM (optional) | Anthropic Claude, Google Gemini (with 3-tier fallback), OpenAI-compatible APIs |
| Calendar | Google Calendar API (OAuth2) |
| Migrations | Alembic |
| Frontend | Next.js (Turborepo monorepo) |
| Infrastructure | Docker Compose |

## Project Structure

```
founder-os/
├── apps/
│   ├── api/                    # Python backend (FastAPI)
│   │   ├── app/
│   │   │   ├── main.py         # FastAPI app + lifespan (scheduler, Redis, DB)
│   │   │   ├── config.py       # Settings (pydantic-settings)
│   │   │   ├── database.py     # Async SQLAlchemy engine
│   │   │   ├── redis.py        # Async Redis client
│   │   │   ├── auth.py         # Clerk JWT verification
│   │   │   ├── models.py       # 24-table ORM (pgvector)
│   │   │   ├── planner_models_db.py  # 4 planner/memory tables
│   │   │   ├── scheduler.py    # APScheduler (weekly plan cron)
│   │   │   ├── celery_app.py   # Celery config + queues
│   │   │   ├── user_store.py   # PostgreSQL-backed user profile store
│   │   │   ├── api/
│   │   │   │   ├── routes.py          # Health + auth routes
│   │   │   │   ├── agent_routes.py    # Agent + orchestration endpoints
│   │   │   │   ├── approval_routes.py # Human-in-the-loop approval API
│   │   │   │   ├── queue_routes.py    # Background task queue API
│   │   │   │   ├── knowledge_routes.py # Knowledge base CRUD + search
│   │   │   │   ├── planner_routes.py  # Weekly planner + Google Calendar
│   │   │   │   ├── memory_routes.py   # Temporal knowledge graph API
│   │   │   │   └── test_routes.py     # Dev/test endpoints
│   │   │   ├── agents/
│   │   │   │   ├── orchestrator.py    # Top-level Orchestrator (Stripe Minions)
│   │   │   │   ├── base.py           # BaseAgent (core)
│   │   │   │   ├── agents.py         # 6 specialist agents + registry
│   │   │   │   ├── llm.py            # LLM provider abstraction (6 providers)
│   │   │   │   ├── tool_protocol.py  # MCP-compatible tool registry + closures
│   │   │   │   ├── mcp_adapter.py    # MCP stdio/SSE clients
│   │   │   │   ├── tools.py          # @tool decorator + catalog
│   │   │   │   ├── builtin_tools.py  # 12 built-in tools (incl. delegate_task)
│   │   │   │   ├── memory.py         # 4-layer memory system
│   │   │   │   ├── approval.py       # Approval gate (3-tier risk classification)
│   │   │   │   ├── planner_models.py # Structured plan models + ICE scoring
│   │   │   │   ├── router.py         # A2A agent router
│   │   │   │   ├── execution.py      # Step-based execution engine
│   │   │   │   ├── event_bus.py      # Redis pub/sub event bus
│   │   │   │   ├── registry.py       # Agent factory + orchestrator wiring
│   │   │   │   ├── api_client.py     # External API client utilities
│   │   │   │   └── mock_data.py      # Mock data factories for dev/testing
│   │   │   └── integrations/
│   │   │       └── calendar_integration.py  # Google Calendar OAuth + CRUD
│   │   ├── schema.sql               # Full DDL (24 tables + views + indexes + seeds)
│   │   ├── migrations/              # SQL migration files
│   │   ├── alembic/                 # Alembic DB migrations
│   │   └── requirements.txt
│   ├── web/                    # Next.js frontend (dashboard — WIP)
│   └── docs/                   # Next.js docs site (WIP)
├── packages/
│   ├── ui/                     # Shared React components
│   ├── eslint-config/          # Shared ESLint config
│   └── typescript-config/      # Shared TS config
├── docker-compose.yml          # PostgreSQL + Redis
├── start.sh                    # Quick start script
└── turbo.json                  # Turborepo config
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

# 6. (Optional) Start Celery worker for background tasks
celery -A app.celery_app worker --loglevel=info -Q default,agents,orchestrator

# 7. Check health
curl http://localhost:8000/api/health

# 8. Talk to the Orchestrator
curl -X POST http://localhost:8000/api/agents/orchestrate \
  -H "Content-Type: application/json" \
  -d '{"message": "Plan my week — I need to ship v2.0, write a blog post, and prep for investor calls"}'
```

### Google Calendar Setup (Optional)

To enable weekly plan → Google Calendar sync:

1. Create a Google Cloud project with Calendar API enabled
2. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`
3. Connect via `POST /api/planner/connect` (OAuth2 flow)
4. Plans will auto-sync every Monday at 08:00 AM IST

---

## Philosophy

> "The best startup tool is one that does the work, not one that helps you do the work."

Founder OS exists because we believe:

1. **AI agents should be systems, not features.** Not a chat widget bolted onto a dashboard — a persistent, intelligent backend that operates your business around the clock.
2. **Workflows should generate themselves.** If you have to design an automation by hand, the tool has already failed. The system should observe your business, understand what needs doing, and compose the right agent workflow automatically.
3. **Automation should scale with you.** Day 1: simple single-agent tasks. Month 6: complex cross-functional orchestrations. The system grows because it learns — not because you wired up more nodes in a graph editor.

Every design decision flows from one question: *what would a tireless, infinitely patient, always-available co-founder do?*

---

## License

MIT
