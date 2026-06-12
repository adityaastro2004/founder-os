"""
Clerk JWT verification for FastAPI.

Fetches Clerk's JWKS (JSON Web Key Set) and validates incoming Bearer tokens.
Exposes two FastAPI dependencies:

  - require_auth   → returns ClerkUser or raises 401
  - optional_auth  → returns ClerkUser | None (no error if missing)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

# ── Bearer token extractor ──────────────────────────────
_bearer_scheme = HTTPBearer(auto_error=False)

# ── JWKS cache ──────────────────────────────────────────
_jwks_cache: dict = {}
_jwks_cache_expiry: float = 0
_JWKS_TTL_SECONDS = 3600  # re-fetch keys every hour


async def _get_jwks() -> dict:
    """Fetch and cache Clerk's JWKS."""
    global _jwks_cache, _jwks_cache_expiry

    if _jwks_cache and time.time() < _jwks_cache_expiry:
        return _jwks_cache

    settings = get_settings()
    if not settings.CLERK_JWKS_URL:
        raise RuntimeError(
            "CLERK_JWKS_URL is not set. "
            "Add it to your .env (find it in the Clerk dashboard → API Keys)."
        )

    async with httpx.AsyncClient() as client:
        resp = await client.get(settings.CLERK_JWKS_URL, timeout=10)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_cache_expiry = time.time() + _JWKS_TTL_SECONDS

    return _jwks_cache


def _get_signing_key(jwks: dict, token: str) -> jwt.algorithms.RSAAlgorithm:
    """Match the token's `kid` header against the JWKS keys."""
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")

    for key_data in jwks.get("keys", []):
        if key_data["kid"] == kid:
            return jwt.algorithms.RSAAlgorithm.from_jwk(key_data)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token signing key not found in JWKS.",
    )


# ── Decoded user payload ────────────────────────────────
@dataclass
class ClerkUser:
    """Lightweight representation of the authenticated Clerk user."""

    user_id: str  # Clerk's `sub` claim
    session_id: str | None = None
    org_id: str | None = None
    org_role: str | None = None
    email: str | None = None
    claims: dict = field(default_factory=dict)


def _parse_clerk_token(payload: dict) -> ClerkUser:
    """Build a ClerkUser from JWT claims."""
    return ClerkUser(
        user_id=payload["sub"],
        session_id=payload.get("sid"),
        org_id=payload.get("org_id"),
        org_role=payload.get("org_role"),
        email=payload.get("email"),
        claims=payload,
    )


# ── Token verification ──────────────────────────────────
async def _verify_token(token: str) -> ClerkUser:
    """Verify a Clerk JWT and return the decoded user."""
    settings = get_settings()

    jwks = await _get_jwks()
    public_key = _get_signing_key(jwks, token)

    decode_options: dict = {}
    decode_kwargs: dict = {
        "algorithms": ["RS256"],
        "issuer": settings.CLERK_ISSUER,
        "options": decode_options,
    }
    if settings.CLERK_AUDIENCE:
        decode_kwargs["audience"] = settings.CLERK_AUDIENCE
    else:
        decode_options["verify_aud"] = False

    try:
        payload = jwt.decode(token, public_key, **decode_kwargs)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
        )
    except jwt.InvalidIssuerError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token issuer.",
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        )

    return _parse_clerk_token(payload)


# ── Dev-only test-user bypass ────────────────────────────
def _dev_test_user(request: Request) -> ClerkUser | None:
    """Accept an ``x-test-user`` header as the identity — ONLY in development.

    Hard-gated on ``APP_ENV == "development"`` (the same gate that mounts the
    unauthenticated dev test routes in main.py). Lets the local test scripts
    (test_system / test_memory / test_rag_pipeline / test_content_agent) exercise
    authenticated endpoints without minting Clerk JWTs. Never active in production.
    """
    settings = get_settings()
    if settings.APP_ENV != "development":
        return None
    test_user = request.headers.get("x-test-user")
    if not test_user:
        return None
    return ClerkUser(user_id=test_user, email=f"{test_user}@test.local")


# ── FastAPI dependencies ─────────────────────────────────
async def require_auth(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer_scheme),
    ] = None,
) -> ClerkUser:
    """Dependency that **requires** a valid Clerk JWT.

    Usage:
        @router.get("/me")
        async def me(user: ClerkUser = Depends(require_auth)):
            return {"user_id": user.user_id}
    """
    dev_user = _dev_test_user(request)
    if dev_user is not None:
        return dev_user
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await _verify_token(credentials.credentials)


async def optional_auth(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer_scheme),
    ] = None,
) -> ClerkUser | None:
    """Dependency that returns the user if a valid token is present, else None.

    Usage:
        @router.get("/feed")
        async def feed(user: ClerkUser | None = Depends(optional_auth)):
            ...
    """
    dev_user = _dev_test_user(request)
    if dev_user is not None:
        return dev_user
    if credentials is None or not credentials.credentials:
        return None
    try:
        return await _verify_token(credentials.credentials)
    except HTTPException:
        return None
