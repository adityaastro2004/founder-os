# Observability runbook — Grafana Cloud

Founder OS ships metrics to **Grafana Cloud's free tier** via a single Grafana
Alloy container on the EC2 box. See [ADR-018](../../docs/decisions.md) for why
self-hosting Prometheus + Grafana was rejected (~500 MB on a ~1 GB host).

```
api  /metrics ──scrape──▶ alloy ──remote_write──▶ Grafana Cloud
worker ──▶ Redis ──▶ api                              │
                                              dashboards + alerts
```

## What's here

| Path | What it is |
|---|---|
| `alloy/config.alloy` | Collector config — scrape targets, host exporter, remote-write |
| `dashboards/infra-health.json` | Uptime, latency, errors, queues, host resources |
| `dashboards/agent-llm-ops.json` | LLM spend, orchestrator outcomes, approvals, fallbacks |
| `dashboards/business.json` | Users, tasks, State Engine entities, sync freshness |
| `alerts/founder-os.yaml` | Four alert rules (APIDown, HighErrorRate, CeleryBacklog, LLMCostBudget) |

Git is the source of truth. If you edit a dashboard in the Grafana UI, export the
JSON and commit it back, or the next deploy silently reverts your change.

## One-time setup

### 1. Create the stack

Sign up at [grafana.com](https://grafana.com) → create a free stack. From
**Connections → Add new connection → Hosted Prometheus metrics**, generate an
access policy token and note three values:

- the Prometheus **remote-write endpoint** (`https://prometheus-prod-XX-…/api/prom/push`)
- the **username / instance ID** (a number)
- the **token**

Scope the token to `metrics:write` only. It does not need read access — the
dashboards read through Grafana Cloud itself, not through this token.

### 2. Generate a metrics token

This guards `GET /metrics`, which discloses internal route names, traffic volumes
and LLM spend:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. Add the secrets

`METRICS_TOKEN` goes in the repo's **GitHub Actions secrets**, from where
[`scripts/deploy-server.sh`](../../scripts/deploy-server.sh) syncs it into the
server's `apps/api/.env` on every deploy — so rotating it is a secret update plus
a re-run.

The three Grafana Cloud values are **not** synced that way. `deploy-server.sh`
restricts synced values to `[A-Za-z0-9._:/-]` because they pass through `sed`, and
Grafana tokens contain `=` and `+`. Loosening that validation for an observability
feature would be the wrong trade, so those three are provisioned by hand, once
(below). They rotate rarely.

| Value | Where it lives | Used by |
|---|---|---|
| `METRICS_TOKEN` | Actions secret → `apps/api/.env` | the API (guards `/metrics`) **and** Alloy (sends it) |
| `GRAFANA_CLOUD_PROM_URL` | `/etc/founder-os/alloy.env` on the box | Alloy |
| `GRAFANA_CLOUD_PROM_USER` | same | Alloy |
| `GRAFANA_CLOUD_API_KEY` | same | Alloy |

Never put any of these in `apps/api/app/config.py`. Provider keys were committed
that way once and were auto-revoked within days.

### 4. Start Alloy

**Which topology you are on matters.** The live instance runs the API as the
`founder-api` **systemd** unit, *not* under `docker-compose.prod.yml` (see
[DEPLOY.md](../../DEPLOY.md) — Parts 1–3 are the self-host recipe, Part 4 is what
actually runs). Pick the matching path.

#### Live EC2 (systemd) — the hosted instance

Alloy runs as a host-network container alongside the existing Postgres/Redis
containers. One-time setup:

```bash
sudo install -d -m 750 /etc/founder-os
sudo tee /etc/founder-os/alloy.env >/dev/null <<'ENV'
FOS_API_TARGET=localhost:8000
METRICS_TOKEN=<same value as the Actions secret>
GRAFANA_CLOUD_PROM_URL=https://prometheus-prod-XX-.../api/prom/push
GRAFANA_CLOUD_PROM_USER=<instance id>
GRAFANA_CLOUD_API_KEY=<token>
ENV
sudo chmod 600 /etc/founder-os/alloy.env

docker run -d --name founder-os-alloy --restart unless-stopped \
  --network host \
  --env-file /etc/founder-os/alloy.env \
  -v /home/ubuntu/founder-os/ops/grafana/alloy/config.alloy:/etc/alloy/config.alloy:ro \
  -v founder-os-alloy-data:/var/lib/alloy/data \
  -v /proc:/host/proc:ro -v /sys:/host/sys:ro -v /:/rootfs:ro \
  grafana/alloy:v1.11.0 \
  run --server.http.listen-addr=127.0.0.1:12345 \
      --storage.path=/var/lib/alloy/data /etc/alloy/config.alloy
```

Deliberately **not** wired into `deploy-server.sh`: that script runs on every
push, and an Alloy container that crash-loops on a missing credential must not be
able to fail a product deploy. This is one-time setup, so it stays manual. After a
`config.alloy` change, `docker restart founder-os-alloy`.

Verify:

```bash
curl -fsS -H "Authorization: Bearer $METRICS_TOKEN" http://localhost:8000/metrics | head
docker logs --tail=50 founder-os-alloy
```

#### docker-compose.prod.yml (self-host recipe)

Alloy sits behind the `metrics` profile, so an unconfigured stack boots cleanly
instead of crash-looping a collector with nowhere to ship to:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml \
  --profile metrics up -d alloy

docker compose -f docker-compose.prod.yml logs --tail=50 alloy
```

Either way, in Grafana Cloud **Explore → `up{job="founder-os-api"}`** should
return 1 within a minute.

### 5. Import dashboards

**Dashboards → New → Import → Upload JSON**, once per file in `dashboards/`. Each
uses a `$datasource` variable, so pick your Prometheus data source on import — no
editing required.

### 6. Enable alerts

Edit `alerts/founder-os.yaml` and replace `DATASOURCE_UID` with your Prometheus
data source UID (**Connections → Data sources →** click it → the UID is in the
URL). Then **Alerting → Alert rules → Import**.

Set a contact point under **Alerting → Contact points** (email works on the free
tier) and point the `Founder OS` folder's notification policy at it.

The `LLMCostBudget` threshold ships as a placeholder `$10/day`. Watch the spend
panel for a week, then set it to about 3× a normal day.

## Operating notes

**Series budget.** The free tier allows 10k active series; current usage is
roughly 2.2k. Check **Billing → Usage** occasionally. If it climbs unexpectedly,
the cause is almost always a new metric label with unbounded values — the same
mistake `route` templating exists to prevent.

**If the box runs low on memory,** drop the host exporter first: delete the
`prometheus.exporter.unix` and its `prometheus.scrape "host"` block from
`config.alloy`. That's ~150 series and the least valuable data collected.

**If `/metrics` returns 401,** the API's `METRICS_TOKEN` and Alloy's disagree.
They read the same variable, so this means `.env.production` was updated without
restarting one of the two containers.

**If `/metrics` returns 404,** either `METRICS_ENABLED=false`, or `METRICS_TOKEN`
is empty in a non-development environment — in which case the endpoint is
deliberately not mounted rather than left open. Fail closed, by design.

**Retention is 14 days.** Anything needing a longer horizon belongs in PostHog or
a rollup that does not exist yet.

## What is deliberately not here

Logs (Loki), traces (OTel), and per-user metrics. Per-user product analysis stays
in PostHog: metrics leave the box to a third party, so no user-identifying value
is ever attached as a label. Enforced by a unit test, not by convention.
