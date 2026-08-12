---
id: 028
title: Grafana Cloud observability — metrics, dashboards, alerts
status: in-progress
stage: executor
owner: eng-executor
created: 2026-08-04
dependencies: []
links:
  - docs/superpowers/specs/2026-08-04-grafana-observability-design.md
  - docs/decisions.md#adr-018
---

# 028 — Grafana Cloud observability

## Objective
Give the founder one place to see whether Founder OS is up, fast, affordable, and
growing — infra health, agent/LLM ops, and business aggregates — plus alerts on the
four failure modes that matter. Production currently runs blind.

## User stories
- As the founder, I want to see API uptime, latency and error rate so I know the
  product is working without SSH-ing to the box.
- As the founder, I want LLM cost per provider per day so a runaway agent loop
  cannot quietly drain my budget.
- As the founder, I want to be emailed when the API is down or the Celery queue
  backs up, so I find out before a user does.

## Acceptance criteria
- [ ] `GET /metrics` returns Prometheus exposition text with HTTP, Celery, LLM, and
      business metrics.
- [ ] `/metrics` is 401 without the bearer token, 200 with it, and absent (404) when
      `METRICS_ENABLED=false`.
- [ ] Route labels use the FastAPI route template — `/agents/{id}` — never raw paths.
- [ ] No metric label anywhere is `user_id`, `email`, `clerk_user_id`, or free text.
- [ ] Celery task counters recorded by the worker appear in the API's `/metrics`.
- [ ] Three dashboard JSONs and four alert rules committed under `ops/grafana/`.
- [ ] Alloy service in `docker-compose.prod.yml`, not exposed by Caddy.
- [ ] `pytest` unit tier green; `ruff` clean.

## Success metrics
- Founder can answer "is it up / what did it cost yesterday" in <30s from one tab.
- Total active series stays under ~3k (free-tier ceiling 10k).

## Out of scope
Loki/log aggregation, OTel tracing, per-user dashboards, a local-dev Grafana stack,
migrating PostHog events into Prometheus.

## Requirements / open questions
- Founder must create the Grafana Cloud free stack and supply three secrets before
  data flows (documented in `ops/grafana/README.md`). Code ships working without
  them.
- `LLMCostBudget` alert threshold is a placeholder until a cost baseline exists.

---

## Architecture
See ADR-018 and the spec. Summary:
- Data model + Alembic: **none** — no schema change. Business metrics are read-only
  `COUNT` queries over existing tables.
- API: `GET /metrics`, bearer-token guarded, mounted only when `METRICS_ENABLED`.
  Not routed through Caddy.
- File placement: new `apps/api/app/metrics/` package (registry, middleware,
  celery_bridge, business, routes); new top-level `ops/grafana/`.
- Integration points: `main.py` (middleware + router + lifespan job),
  `celery_app.py` (signal import), `app/agents/llm.py` (leaf-provider decorator),
  `app/scheduler.py` (5-min business job).
- Risks: Alloy RAM on a 1 GB box; stale LLM price table; 14-day retention.

## Build notes
- Changed files: see the PR diff.
- How verified: `pytest tests/unit/test_metrics*.py`, `ruff check`.

## Review findings
- Pending.

## QA results
- Pending.

## Security report
- Pending — required (touches auth surface + secrets).
