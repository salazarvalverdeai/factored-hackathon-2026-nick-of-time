"""Public abuse guard (spec 05 AC-18): per-IP and global hourly limits on session creation and agent turns.

The client IP is the peer's address unless the peer is the trusted proxy (Caddy, on the compose network): only then is
the last `X-Forwarded-For` entry read, the one Caddy writes (it drops a client's own X-Forwarded-For since 2.5). The api
port is not published (infra/compose.yml), so only containers on that network reach it. An IPv6 client is counted by
its /64, the block one subscriber usually holds.

[assumption] The counters live in process memory: the api runs one uvicorn worker (apps/api/Dockerfile CMD) on one
EC2 (ADR 0011), so one process sees every request. More workers or hosts would each count alone (move them to the store).
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import os
import re
import threading
from collections import deque
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

WINDOW = dt.timedelta(hours=1)
# [assumption] limits for the public demo; each overridable by its environment variable
LIMITS = {"session": ("RATE_SESSIONS_PER_IP_HOUR", 10, "RATE_SESSIONS_GLOBAL_HOUR", 300),
          "turn": ("RATE_TURNS_PER_IP_HOUR", 60, "RATE_TURNS_GLOBAL_HOUR", 1500)}
TRUSTED_PROXIES = "172.16.0.0/12,192.168.0.0/16"      # [assumption] Docker's default bridge pools, where Caddy runs
ROUTES = (("POST", re.compile(r"/api/sessions"), "session"),
          ("POST", re.compile(r"/api/agent/threads(/[^/]+/runs/stream)?"), "turn"),
          ("POST", re.compile(r"/api/sessions/[^/]+/synthetic-charge"), "turn"))     # demo type C (spec 05 AC-19)
MESSAGE = ("Recibimos muchas solicitudes desde tu conexión. Intenta de nuevo en unos minutos. / Recebemos muitas "
           "solicitações da sua conexão. Tente novamente em alguns minutos.")


def trusted_networks(spec: str | None = None) -> list:
    raw = (os.getenv("TRUSTED_PROXY_CIDRS") or TRUSTED_PROXIES) if spec is None else spec
    return [ipaddress.ip_network(part.strip()) for part in raw.split(",") if part.strip()]


def _key(address: str) -> str | None:
    """The counting key of an address: itself for IPv4, its /64 for IPv6; None when it is not an address."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return None
    return str(ipaddress.ip_network(f"{ip}/64", strict=False)) if ip.version == 6 else str(ip)


def client_ip(request: Request, trusted: list) -> str:
    """The peer, or the proxy's last X-Forwarded-For entry when the peer is a trusted proxy (never the client's)."""
    peer = request.client.host if request.client else "unknown"
    try:
        from_proxy = any(ipaddress.ip_address(peer) in net for net in trusted)
    except ValueError:
        from_proxy = False
    forwarded = _key(request.headers.get("x-forwarded-for", "").split(",")[-1].strip())
    return forwarded if from_proxy and forwarded else (_key(peer) or peer)


class RateLimiter:
    """Sliding one-hour windows per (bucket, ip) and per bucket; a refused request is not counted."""

    def __init__(self, now: Callable[[], dt.datetime], limits: dict[str, tuple[int, int]] | None = None) -> None:
        self.now, self._lock, self._hits = now, threading.Lock(), {}
        self.limits = limits or {b: (int(os.getenv(ip_env) or ip_n), int(os.getenv(all_env) or all_n))
                                 for b, (ip_env, ip_n, all_env, all_n) in LIMITS.items()}

    def _window(self, key: tuple, start: dt.datetime) -> deque:
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= start:
            hits.popleft()
        return hits

    def hit(self, bucket: str, ip: str) -> int | None:
        """None when allowed (and counted), else the seconds until the oldest counted hit leaves the window."""
        per_ip, overall = self.limits[bucket]
        with self._lock:
            t = self.now()
            start = t - WINDOW
            mine, every = self._window((bucket, ip), start), self._window((bucket, None), start)
            for hits, cap in ((mine, per_ip), (every, overall)):
                if len(hits) >= cap:
                    return max(1, int((hits[0] - start).total_seconds()) + 1)
            mine.append(t)
            every.append(t)
            if len(self._hits) > 10_000:                  # forget idle addresses
                self._hits = {k: v for k, v in self._hits.items() if v and v[-1] > start}
            return None


def install(app: FastAPI, now: Callable[[], dt.datetime]) -> RateLimiter:
    limiter, trusted = RateLimiter(now), trusted_networks()
    app.state.limiter = limiter

    @app.middleware("http")
    async def _abuse_guard(request: Request, call_next):
        bucket = next((b for m, path, b in ROUTES if request.method == m and path.fullmatch(request.url.path)), None)
        if bucket is not None:
            wait = limiter.hit(bucket, client_ip(request, trusted))
            if wait is not None:
                return JSONResponse({"code": "RATE_LIMITED", "policy_id": None, "message": MESSAGE}, status_code=429,
                                    headers={"Retry-After": str(wait)})
        return await call_next(request)

    return limiter
