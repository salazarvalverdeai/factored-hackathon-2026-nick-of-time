"""Placeholder API for spec 06: serves only GET /api/health until spec 05 ships the real backend.

The workflow builds this image only while apps/api/Dockerfile does not exist (see .github/workflows/deploy.yml).
Standard library only, so the image has no dependencies to maintain.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping

# Field name in /api/health -> environment variable written by infra/deploy.sh.
HEALTH_FIELDS = {
    "version": "APP_VERSION",
    "git_sha": "GIT_SHA",
    "gold_version": "GOLD_VERSION",
    "policies_version": "POLICIES_VERSION",
    "platform_revision": "PLATFORM_REVISION",
}


def health_payload(env: Mapping[str, str]) -> dict:
    """CONTRIBUTING §7. A value that is not known yet is null, never invented (spec 06 AC-06)."""
    payload: dict = {"status": "ok", "service": "api-placeholder"}
    for field, var in HEALTH_FIELDS.items():
        payload[field] = env.get(var) or None
    return payload


def route(method: str, path: str, env: Mapping[str, str]) -> tuple[int, dict]:
    if method == "GET" and path.split("?", 1)[0] == "/api/health":
        return 200, health_payload(env)
    return 404, {"error": "not_found"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        status, body = route("GET", self.path, os.environ)
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:  # one line per request on stdout, no client data beyond the path
        print(f"{self.command} {self.path.split('?', 1)[0]} -> {args[1] if len(args) > 1 else ''}", flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8000"))), Handler).serve_forever()
