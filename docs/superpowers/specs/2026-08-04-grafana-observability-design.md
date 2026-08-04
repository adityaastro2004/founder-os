# Grafana observability for Founder OS — design

**Date:** 2026-08-04
**Status:** Approved (founder, section-by-section)
**ADR:** ADR-018
**Task:** `tasks/active/026-grafana-observability.md`

---

## 1. Problem

Founder OS runs blind in production. There is no way to answer "is the API up and
fast", "did the Celery queue back up", "how much did the LLM providers cost
yesterday", or "how many users are actually active" without SSH-ing to the box and
reading logs. PostHog covers product funnels but nothing operational, and it cannot
alert on a dead API.

## 2. Goals

1. Infra health — request rate, latency, errors, queue depth, host resources.
2. Agent + LLM ops — orchestrator outcomes, provider cost/latency/failures.
3. Product/business aggregates — users, tasks, State Engine volume, sync freshness.
4. Alerting on the four failure modes that matter, delivered to email.

## 3. Non-goals (explicit — do not creep)

- Log aggregation (Loki) or distributed tracing (OTel spans).
- Per-user dashboards or any per-user metric label.
- A local-dev Grafana/Prometheus stack.
- Migrating PostHog events into Prometheus. The two systems stay separate:
  **PostHog = per-user product behaviour, Grafana = aggregate operations.**

## 4. Constraints that drove the design

| Constraint | Consequence |
|---|---|
| EC2 free tier, ~1 GB RAM, already runs Caddy+Postgres+Redis+api+worker | Self-hosted Prometheus+Grafana (~500 MB) would OOM the box → **Grafana Cloud free tier**, only a ~80 MB Alloy agent runs locally |
| Grafana Cloud free tier = 10k active series, 14-day retention | Label cardinality is a hard budget, not a style preference (§6) |
| Prod uvicorn is single-process | Plain in-process `prometheus_client` registry works; no `PROMETHEUS_MULTIPROC_DIR` needed |
| Celery worker is a separate container, prefork concurrency=4 | Cannot host an in-process registry sanely → worker publishes to Redis, API renders (§5) |
| No Celery beat in prod; APScheduler already runs in the API process | Business-gauge refresh is an APScheduler job, not a new beat container |
| `app/redis.py` client is async; `prometheus_client` collectors are sync | Snapshot-then-collect split (§5.2) |
| Provider keys were leaked via `config.py` once (2026-07-14) | Grafana Cloud credentials live only in `.env.production` / Actions secrets, never in `config.py` |

## 5. Architecture

### 5.1 Topology

```
┌─ EC2 (docker compose) ───────────────────────────┐
│  api ── GET /metrics  (in-process registry)      │
│   ├ MetricsMiddleware   rate / latency / status  │
│   ├ record_llm_call()   tokens / cost / tier     │
│   ├ APScheduler 5 min   business gauges ← PG     │
│   └ CeleryCollector     celery counters ← Redis  │
│  worker ── celery signals → Redis hash           │
│  alloy ── scrape api:8000/metrics                │
│        ── prometheus.exporter.unix (host)        │
└──────────────────│───────────────────────────────┘
                   ▼ remote_write (HTTPS + token)
            Grafana Cloud (free: 10k series, 14d)
```

Alloy scrapes `api:8000` over the compose network. `/metrics` is **not** added to
the Caddyfile, so it is unreachable from the internet.

### 5.2 The worker-metrics gap

The worker cannot expose an in-process registry (prefork spawns 4 children, each
with its own memory). Three options were weighed:

| | Approach | Verdict |
|---|---|---|
| A | Celery signals → Redis hash; API reads and re-emits | **Chosen.** One scrape target, no new container, no multiprocess shim, counters survive restarts |
| B | `start_http_server` inside the worker | Rejected — prefork needs `PROMETHEUS_MULTIPROC_DIR` + shared tmpfs; real complexity for no gain |
| C | Pushgateway | Rejected — another container on a 1 GB box, and the documented anti-pattern for this case |

Because `app/redis.py` is async-only and `prometheus_client`'s `collect()` is a
sync generator, A is implemented as a **snapshot-then-collect** split:

1. The `async def /metrics` handler awaits `snapshot_celery_metrics(redis)`, which
   reads the Redis hashes into a module-level dict.
2. `generate_latest(REGISTRY)` then runs `CeleryCollector.collect()`, which reads
   that dict synchronously and yields `CounterMetricFamily` / `GaugeMetricFamily`.

This keeps proper counter semantics (rather than faking counters with gauges) with
no second Redis connection pool and no async call inside `collect()`.

### 5.3 Module layout

```
apps/api/app/metrics/
  __init__.py        public surface: REGISTRY, render(), record_llm_call(), ...
  registry.py        metric objects + one CollectorRegistry; no import side effects
  middleware.py      MetricsMiddleware — route template, latency, in-flight
  celery_bridge.py   worker-side signal handlers → Redis;  API-side CeleryCollector
  business.py        collect_business_metrics() — the 5-minute Postgres COUNTs
  routes.py          GET /metrics, bearer-token guarded
```

A package rather than one module because these are five separate concerns and
`celery_bridge` is imported by a **different process** than the rest — splitting
keeps the worker from importing FastAPI middleware.

## 6. Metric catalog and series budget

Free tier ceiling is 10k active series; exceeding it silently drops data.

**HTTP** — `fos_http_requests_total{route,method,status_class}` (~600),
`fos_http_request_duration_seconds{route}` (~100 routes × 12 buckets = 1200),
`fos_http_requests_in_flight` (1).

`route` is the **FastAPI route template** (`/agents/{agent_id}`), never the raw
path — raw paths are unbounded cardinality and would exhaust the budget in a day.
Unmatched requests collapse to `route="__unmatched__"`. The latency histogram
deliberately carries only `route` (no method/status) to keep bucket multiplication
in check.

**Celery** — `fos_celery_tasks_total{task,queue,state}`,
`fos_celery_task_duration_seconds_sum/count{task}`, `fos_celery_queue_depth{queue}`
(read live via Redis `LLEN`). ~30 series.

**Agent + LLM** — `fos_llm_requests_total{provider,model,outcome}`,
`fos_llm_tokens_total{provider,model,direction}`,
`fos_llm_cost_usd_total{provider,model}`,
`fos_llm_request_duration_seconds{provider}`,
`fos_llm_fallback_total{from_provider,to_provider}`,
`fos_orchestrator_runs_total{outcome}`, `fos_approval_decisions_total{decision}`.
~200 series.

**Business** (5-min APScheduler job) — `fos_users_total`, `fos_users_active_7d`,
`fos_tasks_by_status{status}`, `fos_state_entities{entity_type}`,
`fos_integration_sync_age_seconds{integration_type}`. ~30 series.

**Host** (Alloy unix exporter, collectors filtered to
`cpu,meminfo,diskstats,filesystem,loadavg`) — ~150 series.

**Total ≈ 2.2k of 10k.** Headroom for growth.

### 6.1 Label policy (hard rule)

No `user_id`, `email`, `org`, `clerk_user_id`, or any free-text value may appear as
a metric label. This is simultaneously a cardinality control and a PII control —
metrics leave the box to a third party, so the constraint is at least as strict as
`app/log_sanitize.py`. Enforced by a unit test that asserts the registry's label
names against a denylist.

## 7. Instrumentation points

- **HTTP** — `MetricsMiddleware`, added in `main.py` inside CORS so it observes real
  handler latency.
- **LLM** — an `@instrumented_generate` decorator applied to the four *leaf*
  providers (`OllamaProvider`, `AnthropicProvider`, `OpenAICompatibleProvider`,
  `GeminiNativeProvider`). `GeminiWithFallback` is deliberately **not** decorated —
  it delegates to decorated leaves, so decorating it too would double-count; it
  instead records `fos_llm_fallback_total` on each tier transition.
  An explicit decorator was chosen over `__init_subclass__` auto-wrapping because
  this codebase prefers explicit registration (see the `celery.conf.imports`
  comment in `celery_app.py`).
- **Cost** — a `_PRICE_PER_MTOK` table in `registry.py` maps `(provider, model)` to
  USD per million tokens. Unknown models record tokens but zero cost. This table
  goes stale when providers reprice; it lives in exactly one place with a comment
  saying so.
- **Celery** — `task_prerun` / `task_postrun` / `task_failure` signals.
- **Orchestrator / approval gate** — recorded at the graph terminal node and in
  `ApprovalGate`.

All recording is wrapped so an instrumentation bug can never break a request or an
agent run — the same fail-open discipline as `RateLimitMiddleware`.

## 8. Security

- `/metrics` exposes internal route names, traffic volumes, and cost data. It is
  guarded by a `METRICS_TOKEN` bearer check, is absent from the Caddyfile, and is
  reachable only on the compose network.
- Token comparison uses `hmac.compare_digest`, never `==`.
- When `METRICS_ENABLED=false` the route is not mounted at all (404, not 401).
- In non-development environments an empty `METRICS_TOKEN` disables the endpoint
  rather than leaving it open — fail closed.
- `GRAFANA_CLOUD_API_KEY` is scoped `metrics:write` only, stored in GitHub Actions
  secrets and synced to `.env.production` by `scripts/deploy-server.sh`. Never in
  `config.py`, never committed.

Mandatory `eng-security` review per CLAUDE.md §7 (this touches auth surface and
secrets).

## 9. Dashboards

Provisioned from JSON committed at `ops/grafana/dashboards/`. Git is the source of
truth; UI edits must be exported back.

1. **Infra health** — stat row (uptime, RPS, p95, 5xx rate), then request rate by
   status class, latency p50/p95/p99, in-flight, queue depth by queue, task failure
   rate, host CPU/mem/disk.
2. **Agent + LLM ops** — LLM cost/day by provider as the hero panel, orchestrator
   runs by outcome, agent task success/failure, tokens in/out, p95 provider latency,
   fallback transitions, approval-gate decisions.
3. **Business** — users total + active-7d, tasks by status, State Engine entities by
   type, integration sync staleness. Deliberately thin; PostHog keeps funnels.

## 10. Alerts

Provisioned from `ops/grafana/alerts/founder-os.yaml`, contact point = email.

| Alert | Condition | For |
|---|---|---|
| `APIDown` | `up{job="founder-os-api"} == 0` | 2m |
| `HighErrorRate` | 5xx ratio > 5% | 5m |
| `CeleryBacklog` | `fos_celery_queue_depth > 50` | 10m |
| `LLMCostBudget` | `increase(fos_llm_cost_usd_total[24h]) > $N` | 15m |

The `for` durations are load-bearing — without them a single blip pages the
founder. `$N` is a placeholder set once a cost baseline exists.

`APIDown` sets `noDataState: Alerting`. A total EC2 outage kills Alloy too, so the
series simply stops arriving; without that setting a dead box would alert on
nothing.

## 11. Testing

Unit tier (no services, per `standards/testing.md`):

- Route-template labelling: `/agents/123` and `/agents/456` produce **one** series.
- Label denylist: no PII-ish label name anywhere in the registry.
- `/metrics` → 401 without token, 200 with, 404 when `METRICS_ENABLED=false`.
- `CeleryCollector` parses the Redis hash, and tolerates a missing/empty hash (the
  worker may never have started).
- Cost calculation for a known model, and zero-cost for an unknown one.
- Business collector emits every declared gauge; query shapes verified against ORM.
- The LLM decorator never raises into the caller when recording fails.

Regression tier: the middleware changes no existing response body or status code.

## 12. Risks accepted

1. Alloy adds ~80 MB RSS to a ~1 GB box. Tolerable. If it OOMs, drop the unix
   exporter first (~150 series, least value per byte).
2. The LLM price table goes stale on provider repricing. One dict, one comment.
3. 14-day retention. Longer trends live in PostHog or a future rollup — not solved
   here.

## 13. Rollout

1. Merge with `METRICS_ENABLED=true` but no Grafana Cloud credentials — `/metrics`
   works, Alloy is not yet started. Zero risk to the running service.
2. Create the Grafana Cloud free stack, add the three secrets, start Alloy.
3. Import dashboards, confirm data, then enable alert rules.

Steps 2–3 are founder actions documented in `ops/grafana/README.md`; they need a
Grafana Cloud account and cannot be automated from here.
