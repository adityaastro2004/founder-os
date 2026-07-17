"""
SSRF protection for outbound crawler/fetch requests.

The crawler fetches URLs that originate from user-supplied config (competitor
websites, RSS feeds). Without validation, an authenticated user could point the
crawler at internal services — most dangerously the cloud instance-metadata
endpoint (``http://169.254.169.254/...``) on EC2, which would leak IAM
credentials into stored research findings. This module blocks that class of
attack by:

  * allowing only ``http`` / ``https`` schemes, and
  * resolving the target hostname and refusing any address that is loopback,
    private, link-local, reserved, multicast, or unspecified — checked BEFORE
    the request, and re-checked on every redirect hop.

See standards/security.md ("Input handling"). Fail closed: on any resolution or
validation error the request is refused, not sent.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Manual redirect cap (we follow redirects ourselves so each hop is validated).
MAX_REDIRECTS = 5

_ALLOWED_SCHEMES = {"http", "https"}


class SSRFError(ValueError):
    """Raised when a URL targets a disallowed scheme or a non-public address."""


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True if the address must not be reached from the server."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # covers 169.254.0.0/16 → cloud metadata
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def validate_public_url(url: str) -> None:
    """Raise :class:`SSRFError` unless ``url`` is http(s) and resolves to a
    public IP address only. Safe to ``await`` from async request paths."""
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise SSRFError(f"URL scheme not allowed: {scheme or '(none)'}")

    host = parsed.hostname
    if not host:
        raise SSRFError("URL has no host")

    # If the host is already an IP literal, check it directly.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _ip_is_blocked(literal):
            raise SSRFError(f"URL resolves to a non-public address: {host}")
        return

    # Otherwise resolve the hostname and reject if ANY address is non-public.
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, parsed.port or (443 if scheme == "https" else 80))
    except OSError as exc:
        raise SSRFError(f"Could not resolve host {host!r}: {exc}") from exc

    if not infos:
        raise SSRFError(f"Host {host!r} did not resolve to any address")

    for info in infos:
        sockaddr = info[4]
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            raise SSRFError(f"Host {host!r} resolved to an unparseable address")
        if _ip_is_blocked(ip):
            raise SSRFError(f"Host {host!r} resolves to a non-public address: {ip}")


async def safe_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict | None = None,
    max_redirects: int = MAX_REDIRECTS,
) -> httpx.Response:
    """GET ``url`` with SSRF validation on the initial URL and every redirect.

    Redirects are followed manually (``follow_redirects=False``) so each hop's
    target is validated before it is requested — this closes redirect-based
    SSRF where an attacker-controlled host 302s to an internal address.
    """
    current = url
    for _ in range(max_redirects + 1):
        await validate_public_url(current)
        resp = await client.get(current, headers=headers, follow_redirects=False)
        if resp.is_redirect and resp.headers.get("location"):
            current = str(resp.url.join(resp.headers["location"]))
            continue
        return resp
    raise SSRFError(f"Too many redirects (>{max_redirects}) starting from {url}")
