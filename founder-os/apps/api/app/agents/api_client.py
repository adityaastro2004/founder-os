"""
Founder OS — API Client with Retry Logic
==========================================
Production-grade async HTTP client for external API integrations.

Features:
  - Exponential backoff with jitter
  - Circuit breaker (prevents cascading failures)
  - Rate-limit awareness (respects 429 / Retry-After headers)
  - Configurable timeouts, max retries, and retry codes
  - Request / response logging (with sensitive header redaction)
  - Works standalone or as a tool provider for agents

Usage:
    from app.agents.api_client import APIClient, RetryConfig

    client = APIClient(base_url="https://api.example.com",
                       headers={"Authorization": "Bearer xxx"})
    resp = await client.get("/users", params={"limit": 10})
    print(resp.data)  # parsed JSON
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Headers that should be redacted in logs
_SENSITIVE_HEADERS = {"authorization", "x-api-key", "api-key", "cookie", "set-cookie"}


# ============================================================================
# Configuration
# ============================================================================

class RetryStrategy(str, Enum):
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"


@dataclass
class RetryConfig:
    """Controls how and when requests are retried."""
    max_retries: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    jitter: bool = True
    retry_on_status: set[int] = field(
        default_factory=lambda: {429, 500, 502, 503, 504}
    )
    retry_on_timeout: bool = True
    retry_on_connection_error: bool = True


@dataclass
class CircuitBreakerConfig:
    """Prevents cascading failures by opening the circuit after repeated errors."""
    failure_threshold: int = 5          # failures before opening
    recovery_timeout_seconds: float = 30.0  # how long to stay open
    half_open_max_calls: int = 1        # test calls in half-open state


# ============================================================================
# Circuit Breaker
# ============================================================================

class CircuitState(str, Enum):
    CLOSED = "closed"        # normal operation
    OPEN = "open"            # failing — reject immediately
    HALF_OPEN = "half_open"  # testing recovery


class CircuitBreaker:
    """
    In-memory circuit breaker per APIClient instance.

    Closed → OPEN after `failure_threshold` consecutive failures.
    Open → HALF_OPEN after `recovery_timeout_seconds`.
    Half-open → CLOSED on success, → OPEN on failure.
    """

    def __init__(self, config: CircuitBreakerConfig) -> None:
        self._config = config
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._config.recovery_timeout_seconds:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    def allow_request(self) -> bool:
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            return self._half_open_calls < self._config.half_open_max_calls
        return False  # OPEN

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
        elif self._failure_count >= self._config.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker OPENED after %d consecutive failures",
                self._failure_count,
            )


# ============================================================================
# Response wrapper
# ============================================================================

@dataclass
class APIResponse:
    """Normalised response from an API call."""
    status_code: int
    data: Any = None
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    duration_ms: float = 0.0
    retries_used: int = 0
    is_error: bool = False
    error_message: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> Any:
        return self.data


# ============================================================================
# API Client
# ============================================================================

class APIClient:
    """
    Async HTTP client with retry, circuit breaker, and rate-limit handling.

    Args:
        base_url:   Base URL for all requests (e.g. "https://api.stripe.com")
        headers:    Default headers (Authorization, etc.)
        retry:      Retry configuration
        circuit:    Circuit breaker configuration (None to disable)
        timeout:    Request timeout in seconds
        name:       Name for logging (e.g. "stripe", "github")
    """

    def __init__(
        self,
        base_url: str = "",
        headers: dict[str, str] | None = None,
        retry: RetryConfig | None = None,
        circuit: CircuitBreakerConfig | None = None,
        timeout: float = 30.0,
        name: str = "api_client",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_headers = headers or {}
        self.retry_config = retry or RetryConfig()
        self.timeout = timeout
        self.name = name

        self._circuit = CircuitBreaker(circuit) if circuit else CircuitBreaker(
            CircuitBreakerConfig()
        )
        self._client: httpx.AsyncClient | None = None

    # -- Lifecycle -------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.default_headers,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "APIClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # -- HTTP methods ----------------------------------------------------

    async def get(self, path: str, **kwargs: Any) -> APIResponse:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> APIResponse:
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> APIResponse:
        return await self.request("PUT", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> APIResponse:
        return await self.request("PATCH", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> APIResponse:
        return await self.request("DELETE", path, **kwargs)

    # -- Core request with retry logic -----------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        data: Any | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> APIResponse:
        """
        Make an HTTP request with full retry logic.

        Returns an APIResponse (always — never raises for HTTP errors).
        """
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        cfg = self.retry_config
        last_error: Exception | None = None
        retries_used = 0

        for attempt in range(cfg.max_retries + 1):
            # -- Circuit breaker check --
            if not self._circuit.allow_request():
                return APIResponse(
                    status_code=503,
                    is_error=True,
                    error_message=(
                        f"Circuit breaker OPEN for '{self.name}' — "
                        f"failing fast. Will retry after "
                        f"{self._circuit._config.recovery_timeout_seconds}s"
                    ),
                )

            try:
                client = await self._get_client()
                start = time.monotonic()

                response = await client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    data=data,
                    headers=headers,
                    timeout=timeout or self.timeout,
                )

                duration_ms = (time.monotonic() - start) * 1000

                # -- Parse response --
                try:
                    resp_data = response.json()
                except Exception:
                    resp_data = None

                api_resp = APIResponse(
                    status_code=response.status_code,
                    data=resp_data,
                    text=response.text,
                    headers=dict(response.headers),
                    duration_ms=duration_ms,
                    retries_used=retries_used,
                    is_error=response.status_code >= 400,
                    error_message=response.text if response.status_code >= 400 else "",
                )

                # -- Success —
                if response.status_code < 400:
                    self._circuit.record_success()
                    self._log_request(method, url, response.status_code, duration_ms, attempt)
                    return api_resp

                # -- Retryable status code —
                if response.status_code in cfg.retry_on_status:
                    self._circuit.record_failure()
                    retries_used += 1

                    # Respect Retry-After header (rate limiting)
                    delay = self._compute_delay(attempt, response)
                    self._log_retry(method, url, response.status_code, attempt, delay)

                    if attempt < cfg.max_retries:
                        await asyncio.sleep(delay)
                        continue

                # -- Non-retryable error —
                self._log_request(method, url, response.status_code, duration_ms, attempt)
                return api_resp

            except httpx.TimeoutException as exc:
                last_error = exc
                self._circuit.record_failure()
                retries_used += 1
                if cfg.retry_on_timeout and attempt < cfg.max_retries:
                    delay = self._compute_delay(attempt)
                    logger.warning(
                        "[%s] Timeout on %s %s — retry %d/%d in %.1fs",
                        self.name, method, url, attempt + 1, cfg.max_retries, delay,
                    )
                    await asyncio.sleep(delay)
                    continue

            except httpx.ConnectError as exc:
                last_error = exc
                self._circuit.record_failure()
                retries_used += 1
                if cfg.retry_on_connection_error and attempt < cfg.max_retries:
                    delay = self._compute_delay(attempt)
                    logger.warning(
                        "[%s] Connection error on %s %s — retry %d/%d in %.1fs",
                        self.name, method, url, attempt + 1, cfg.max_retries, delay,
                    )
                    await asyncio.sleep(delay)
                    continue

            except Exception as exc:
                last_error = exc
                self._circuit.record_failure()
                logger.exception("[%s] Unexpected error on %s %s", self.name, method, url)
                break

        # -- All retries exhausted --
        return APIResponse(
            status_code=0,
            is_error=True,
            error_message=f"All {cfg.max_retries + 1} attempts failed: {last_error}",
            retries_used=retries_used,
        )

    # -- Retry delay computation -----------------------------------------

    def _compute_delay(
        self,
        attempt: int,
        response: httpx.Response | None = None,
    ) -> float:
        cfg = self.retry_config

        # 1. Check Retry-After header (429 rate limiting)
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return min(float(retry_after), cfg.max_delay_seconds)
                except ValueError:
                    pass

        # 2. Compute based on strategy
        if cfg.strategy == RetryStrategy.EXPONENTIAL:
            delay = cfg.base_delay_seconds * (2 ** attempt)
        elif cfg.strategy == RetryStrategy.LINEAR:
            delay = cfg.base_delay_seconds * (attempt + 1)
        else:  # FIXED
            delay = cfg.base_delay_seconds

        # 3. Cap to max
        delay = min(delay, cfg.max_delay_seconds)

        # 4. Add jitter (±25%)
        if cfg.jitter:
            jitter = delay * 0.25
            delay = delay + random.uniform(-jitter, jitter)

        return max(0.1, delay)

    # -- Logging helpers -------------------------------------------------

    def _log_request(
        self, method: str, url: str, status: int, duration_ms: float, attempt: int,
    ) -> None:
        level = logging.INFO if status < 400 else logging.WARNING
        logger.log(
            level,
            "[%s] %s %s → %d (%.0fms, attempt %d)",
            self.name, method, url, status, duration_ms, attempt + 1,
        )

    def _log_retry(
        self, method: str, url: str, status: int, attempt: int, delay: float,
    ) -> None:
        logger.warning(
            "[%s] %s %s → %d — retrying in %.1fs (attempt %d/%d)",
            self.name, method, url, status, delay,
            attempt + 1, self.retry_config.max_retries,
        )

    def _redact_headers(self, headers: dict[str, str]) -> dict[str, str]:
        return {
            k: ("***" if k.lower() in _SENSITIVE_HEADERS else v)
            for k, v in headers.items()
        }


# ============================================================================
# Pre-built clients for common integrations
# ============================================================================

def create_github_client(token: str) -> APIClient:
    """GitHub REST API v3 client with appropriate retry settings."""
    return APIClient(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        },
        retry=RetryConfig(
            max_retries=3,
            retry_on_status={403, 429, 500, 502, 503},
        ),
        name="github",
    )


def create_slack_client(token: str) -> APIClient:
    """Slack Web API client."""
    return APIClient(
        base_url="https://slack.com/api",
        headers={"Authorization": f"Bearer {token}"},
        retry=RetryConfig(
            max_retries=3,
            retry_on_status={429, 500, 503},
        ),
        name="slack",
    )


def create_linear_client(api_key: str) -> APIClient:
    """Linear GraphQL API client."""
    return APIClient(
        base_url="https://api.linear.app",
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
        retry=RetryConfig(max_retries=2),
        name="linear",
    )


def create_notion_client(token: str) -> APIClient:
    """Notion API client."""
    return APIClient(
        base_url="https://api.notion.com/v1",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
        },
        retry=RetryConfig(max_retries=3),
        name="notion",
    )


def create_generic_client(
    base_url: str,
    headers: dict[str, str] | None = None,
    name: str = "generic",
    *,
    max_retries: int = 3,
    timeout: float = 30.0,
) -> APIClient:
    """Generic API client with sensible defaults."""
    return APIClient(
        base_url=base_url,
        headers=headers,
        retry=RetryConfig(max_retries=max_retries),
        timeout=timeout,
        name=name,
    )
