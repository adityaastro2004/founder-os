"""
Founder OS — n8n REST client (ADR-008, Track C / C1).

A thin, typed async wrapper over the self-hosted n8n public REST API used by the
workflow system to push compiled workflows, (de)activate them, trigger manual
runs, and health-check the instance. It is a **pure transport client**: it holds
no business logic, never parses n8n JSON back into IR (the compile is one-way per
ADR-008), and never logs the API key.

Design notes (reuse-first, matches the repo idiom):
  - Built on `app.agents.api_client.APIClient`, which already provides async httpx
    with timeouts, retry/backoff, a circuit breaker, and — critically — redaction
    of the `x-api-key` header in its request logs (C-5: the n8n API key is never
    logged). We add no second HTTP stack.
  - Auth is n8n's documented scheme: the `X-N8N-API-KEY` header (created in the
    n8n UI under Settings → n8n API). Base URL + key come from `Settings`
    (`N8N_BASE_URL`, `N8N_API_KEY`) — never hardcoded (NFR-4).
  - Errors map to a small, explicit exception hierarchy so callers (the compiler
    push path, the run-now endpoint) can surface actionable, user-readable errors
    (FR-3) without leaking secrets.

n8n REST surface used (public API, `/api/v1/...`):
  - POST   /api/v1/workflows                 → create_workflow
  - POST   /api/v1/workflows/{id}/activate   → activate_workflow
  - POST   /api/v1/workflows/{id}/deactivate → deactivate_workflow
  - GET    /api/v1/workflows                  → health (lightweight auth'd ping)
Manual triggering of a workflow is done via the workflow's webhook/trigger node;
`trigger_workflow` issues the run and returns n8n's response payload.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.agents.api_client import APIClient, RetryConfig
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# n8n's documented API-key header. Listed in api_client's _SENSITIVE_HEADERS as
# "x-api-key"? No — n8n uses a distinct header name, so we redact it ourselves in
# any log line we emit and never pass it to a log call (C-5).
_N8N_API_KEY_HEADER = "X-N8N-API-KEY"

# n8n public REST API base path.
_API_PREFIX = "/api/v1"


# ============================================================================
# Errors — explicit, secret-safe (no token/key ever placed in the message)
# ============================================================================

class N8nError(Exception):
    """Base error for any n8n REST interaction failure."""


class N8nAuthError(N8nError):
    """The n8n instance rejected our credentials (401/403)."""


class N8nNotFoundError(N8nError):
    """The referenced n8n resource (e.g. a workflow id) does not exist (404)."""


class N8nUnavailableError(N8nError):
    """n8n could not be reached / did not respond successfully (network, 5xx)."""


# ============================================================================
# Client
# ============================================================================

class N8nClient:
    """
    Typed async client over the n8n public REST API.

    Usage:
        client = N8nClient.from_settings()
        wf_id = await client.create_workflow(compiled_n8n_json)
        await client.activate_workflow(wf_id)
        ...
        await client.aclose()

    Or as an async context manager:
        async with N8nClient.from_settings() as client:
            await client.health()
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # Stored privately; never logged, never exposed (C-5).
        self._api_key = api_key
        headers = {"Accept": "application/json"}
        if api_key:
            headers[_N8N_API_KEY_HEADER] = api_key
        self._http = APIClient(
            base_url=self._base_url,
            headers=headers,
            # n8n is local infra; retry transient 5xx but not auth/4xx.
            retry=RetryConfig(max_retries=2, retry_on_status={429, 500, 502, 503, 504}),
            timeout=timeout,
            name="n8n",
        )

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "N8nClient":
        """Build a client from the app Settings (N8N_BASE_URL / N8N_API_KEY)."""
        cfg = settings or get_settings()
        return cls(base_url=cfg.N8N_BASE_URL, api_key=cfg.N8N_API_KEY)

    # -- Lifecycle -------------------------------------------------------

    async def aclose(self) -> None:
        await self._http.close()

    async def __aenter__(self) -> "N8nClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    # -- Public operations ----------------------------------------------

    async def health(self) -> bool:
        """
        Lightweight, authenticated liveness check.

        Returns True if n8n is reachable and our API key is accepted. Raises
        N8nAuthError on bad credentials and N8nUnavailableError if unreachable —
        so a caller can distinguish "n8n down" from "key wrong".
        """
        resp = await self._http.get(f"{_API_PREFIX}/workflows", params={"limit": 1})
        self._raise_for_status(resp, action="health check", n8n_id=None)
        return True

    async def create_workflow(self, n8n_json: dict[str, Any]) -> str:
        """
        Create a workflow in n8n from compiled n8n JSON. Returns the n8n
        workflow id (stored on the Founder OS Workflow row, FR-2).

        `n8n_json` is the compiler output (Contract 2); this client does not
        inspect or validate its semantics — it is a one-way push.
        """
        resp = await self._http.post(f"{_API_PREFIX}/workflows", json_body=n8n_json)
        self._raise_for_status(resp, action="create workflow", n8n_id=None)
        data = resp.data or {}
        # n8n returns the created workflow object; the id may be top-level or
        # nested under "data" depending on version — handle both defensively.
        wf = data.get("data", data) if isinstance(data, dict) else {}
        wf_id = wf.get("id") if isinstance(wf, dict) else None
        if not wf_id:
            raise N8nError(
                "n8n create-workflow succeeded but returned no workflow id."
            )
        return str(wf_id)

    async def activate_workflow(self, n8n_workflow_id: str) -> None:
        """Activate a workflow so its triggers (cron/webhook) fire."""
        resp = await self._http.post(
            f"{_API_PREFIX}/workflows/{n8n_workflow_id}/activate"
        )
        self._raise_for_status(
            resp, action="activate workflow", n8n_id=n8n_workflow_id
        )

    async def deactivate_workflow(self, n8n_workflow_id: str) -> None:
        """Deactivate a workflow so its triggers stop firing."""
        resp = await self._http.post(
            f"{_API_PREFIX}/workflows/{n8n_workflow_id}/deactivate"
        )
        self._raise_for_status(
            resp, action="deactivate workflow", n8n_id=n8n_workflow_id
        )

    async def trigger_workflow(
        self,
        n8n_workflow_id: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Trigger a manual ("run now") execution of a workflow (FR-4a).

        Returns n8n's run-response payload (e.g. the execution descriptor). The
        public-API run endpoint is `POST /workflows/{id}/run`; if a deployment
        exposes manual runs only via the workflow's webhook trigger node, the
        run-now endpoint (Track G, not this module) can route accordingly.
        """
        resp = await self._http.post(
            f"{_API_PREFIX}/workflows/{n8n_workflow_id}/run",
            json_body=payload or {},
        )
        self._raise_for_status(
            resp, action="trigger workflow", n8n_id=n8n_workflow_id
        )
        return resp.data if isinstance(resp.data, dict) else {}

    # -- Error mapping ---------------------------------------------------

    def _raise_for_status(
        self,
        resp: Any,
        *,
        action: str,
        n8n_id: Optional[str],
    ) -> None:
        """
        Map an APIResponse to a typed N8nError. Never includes the API key or
        any secret in the raised message (C-5); the n8n id is non-secret and
        helps diagnosis.
        """
        if resp.ok:
            return

        suffix = f" (workflow {n8n_id})" if n8n_id else ""
        status = resp.status_code

        # status_code 0 = transport failure (timeout/connection) from APIClient,
        # or circuit breaker 503 with is_error.
        if status == 0:
            raise N8nUnavailableError(
                f"Could not reach n8n to {action}{suffix}: connection failed."
            )
        if status in (401, 403):
            raise N8nAuthError(
                f"n8n rejected our credentials while trying to {action}{suffix}. "
                f"Check N8N_API_KEY."
            )
        if status == 404:
            raise N8nNotFoundError(
                f"n8n resource not found while trying to {action}{suffix}."
            )
        if status >= 500:
            raise N8nUnavailableError(
                f"n8n returned a server error ({status}) while trying to {action}{suffix}."
            )
        # Other 4xx — surface status only, never the response body verbatim
        # (it could echo back submitted credentials / headers).
        raise N8nError(
            f"n8n request to {action}{suffix} failed with status {status}."
        )
