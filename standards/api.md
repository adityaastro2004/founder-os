# API Standards — Founder OS (FastAPI)

> Conventions for backend routes in `apps/api/app/api/`. Mirror the existing
> `*_routes.py` files; don't invent a new pattern.

## Route module structure

- One concern per file, named `<concern>_routes.py` (e.g. `knowledge_routes.py`,
  `planner_routes.py`). Each exposes a module-level `router = APIRouter(...)`.
- Register the router in `app/main.py` with `app.include_router(...)`. A new route
  module **must** be added there or it won't mount.
- Group related endpoints with a shared prefix and tags on the `APIRouter`
  (e.g. `APIRouter(prefix="/api/knowledge", tags=["knowledge"])`).

## Authentication

- Protect every user-facing endpoint with the Clerk dependency:

  ```python
  from app.auth import require_auth, ClerkUser

  @router.get("/me")
  async def me(user: ClerkUser = Depends(require_auth)):
      return {"user_id": user.user_id}
  ```

- Use `optional_auth` only for genuinely public-or-personalized endpoints.
- Scope every query by `user.user_id`. Never trust an ID from the request body to
  identify the caller.
- `test_routes.py` is **dev-only, unauthenticated**, mounted only when
  `APP_ENV=development`. Never add production logic there.

## Request / response

- Use **Pydantic models** for request bodies and response shapes; let FastAPI do
  validation and serialization. Don't hand-parse JSON.
- Return plain dicts / Pydantic models; raise `HTTPException(status_code=..., detail=...)`
  for errors with the correct status (401 auth, 403 forbidden, 404 missing,
  422 validation, 409 conflict).
- Keep responses consistent with sibling routes (field naming, envelope shape).

## Async & data access

- Handlers are `async def`. Use the async DB session and `await` all IO.
- Long-running or multi-agent work goes to **Celery** (`queue_routes.py` pattern):
  enqueue, return a task id, poll for status — don't block the request.

## Streaming (SSE)

- Chat and live updates use Server-Sent Events. Backend streams; the frontend
  consumes via `useEventSource` / `useStreamingFetch`. Match the existing event
  framing used by the chat and agents endpoints.

## Approval-gated actions

- Any endpoint that triggers a MEDIUM/HIGH-risk tool action must route through the
  `ApprovalGate` (`app/agents/approval.py`) and respect `approval_preferences`.
  Never expose a way to execute a HIGH-risk action without approval.

## Checklist for a new endpoint

1. Right module (`*_routes.py`) and registered in `main.py`.
2. `require_auth` (or justified `optional_auth`), queries scoped to `user_id`.
3. Pydantic request/response models.
4. Correct status codes and `HTTPException` on errors.
5. Async IO; heavy work offloaded to Celery.
6. Approval gate honored for risky actions.
7. A test or manual verification ([standards/testing.md](testing.md)).
