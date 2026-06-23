"""
Self-contained tests for the workflow API router (app/api/workflow_routes.py).

No live server / DB: we mount the router on a throwaway FastAPI app, override the
auth + db dependencies, and stub the service layer. This proves the dashboard's
/api/workflows contract is served (the bug was: the router was never registered,
so the Workflows tab 404'd).

Run:  python3 test_workflow_routes.py
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import app.api.workflow_routes as wr
from app.auth import require_auth
from app.database import get_db

RESULTS: list[tuple[str, str, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, "PASS" if cond else "FAIL", detail))


WF_ID = uuid.uuid4()
RUN_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _fake_workflow(**over):
    base = dict(
        id=WF_ID, name="Weekly ops standup", description="Every Monday",
        is_active=True, is_scheduled=True, schedule_cron="0 8 * * 1",
        last_run_at=datetime(2026, 6, 22, tzinfo=timezone.utc),
        total_runs=4, successful_runs=3, n8n_workflow_id=None,
        steps={"ir_version": 1, "trigger": {"type": "manual"},
               "steps": [{"id": "s1", "type": "agent"}, {"id": "s2", "type": "action"}]},
    )
    base.update(over)
    return SimpleNamespace(**base)


def _fake_run(**over):
    base = dict(
        id=RUN_ID, status="running", trigger_type="manual",
        started_at=datetime(2026, 6, 22, tzinfo=timezone.utc), completed_at=None,
        steps_completed=1, steps_failed=0, output_summary=None, error_message=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


class FakeDB:
    async def flush(self):  # run endpoint awaits db.flush()
        return None


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(wr.router)
    app.dependency_overrides[require_auth] = lambda: SimpleNamespace(
        user_id="clerk_abc", email="founder@example.com"
    )

    async def _fake_get_db():
        yield FakeDB()

    app.dependency_overrides[get_db] = _fake_get_db
    return app


async def _run() -> None:
    # Stub the user resolution + service layer the router calls.
    async def fake_user_id(_clerk_id, _db, email=None):
        return USER_ID

    wr.get_or_create_user_id = fake_user_id  # patched name used inside _user_uuid

    async def list_workflows(db, *, user_id):
        check("list: scoped to resolved user", user_id == USER_ID)
        return [_fake_workflow()]

    async def get_workflow(db, *, user_id, workflow_id):
        return _fake_workflow() if str(workflow_id) == str(WF_ID) else None

    async def list_executions(db, *, user_id, workflow_id):
        return [_fake_run()]

    async def get_execution(db, *, user_id, execution_id):
        return _fake_run() if str(execution_id) == str(RUN_ID) else None

    async def create_execution(db, *, user_id, workflow_id, total_steps, **kw):
        check("run: total_steps derived from IR", total_steps == 2, f"got {total_steps}")
        return _fake_run(status="running")

    wr.service.list_workflows = list_workflows
    wr.service.get_workflow = get_workflow
    wr.service.list_executions = list_executions
    wr.service.get_execution = get_execution
    wr.service.create_execution = create_execution

    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        # GET list
        r = await c.get("/api/workflows")
        check("GET /api/workflows → 200", r.status_code == 200, str(r.status_code))
        body = r.json()
        check("list: returns array", isinstance(body, list) and len(body) == 1)
        check("list: workflow shape", body and body[0]["id"] == str(WF_ID)
              and body[0]["schedule_cron"] == "0 8 * * 1"
              and "n8n_workflow_id" in body[0])

        # GET detail (+ steps)
        r = await c.get(f"/api/workflows/{WF_ID}")
        check("GET /api/workflows/{id} → 200", r.status_code == 200, str(r.status_code))
        d = r.json()
        check("detail: includes IR steps envelope",
              isinstance(d.get("steps"), dict) and len(d["steps"]["steps"]) == 2)

        # GET detail not found
        r = await c.get(f"/api/workflows/{uuid.uuid4()}")
        check("GET unknown workflow → 404", r.status_code == 404, str(r.status_code))

        # GET runs list
        r = await c.get(f"/api/workflows/{WF_ID}/runs")
        check("GET /{id}/runs → 200", r.status_code == 200, str(r.status_code))
        check("runs: array of run shape",
              r.json() and r.json()[0]["id"] == str(RUN_ID))

        # GET single run (the /runs/{id} route must not collide with /{id})
        r = await c.get(f"/api/workflows/runs/{RUN_ID}")
        check("GET /runs/{run_id} → 200 (no route collision)",
              r.status_code == 200, str(r.status_code))

        # POST run (no n8n_workflow_id → records a run, no external call)
        r = await c.post(f"/api/workflows/{WF_ID}/run")
        check("POST /{id}/run → 200", r.status_code == 200, str(r.status_code))
        check("run: returns run record", r.json().get("status") == "running")


def main() -> int:
    asyncio.run(_run())
    failed = [r for r in RESULTS if r[1] == "FAIL"]
    for name, status, detail in RESULTS:
        mark = "✓" if status == "PASS" else "✗"
        print(f"  {mark} {name}" + (f"  ({detail})" if detail and status == "FAIL" else ""))
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
