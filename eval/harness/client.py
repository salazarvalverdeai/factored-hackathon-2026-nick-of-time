"""HTTP side of the harness (spec 10 §6): seed a case, send its scripted messages, read FinalState. No text is read."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import httpx

PRODUCTION_HOSTS = ("nickoftime.salazarvalverdeai.com",)     # docs/infrastructure.md: the harness never runs there
TURN_TIMEOUT_S = 60.0                                        # [assumption] spec 10 §5


class HarnessError(RuntimeError):
    """The run set cannot go on (wrong mode, production host, unsealed held-out). Never recorded as a failed run."""


class Api:
    """Client of the evaluation hooks and the agent routes of spec 01 §6.8. `http` is any httpx.Client: a real one
    for a deployed stack, or the test client of the api stub."""

    def __init__(self, http: httpx.Client):
        host = urlsplit(str(http.base_url)).hostname or ""
        if host in PRODUCTION_HOSTS:
            raise HarnessError(f"refusing to run the evaluation against the production host {host}")
        self.http = http

    @classmethod
    def at(cls, base_url: str) -> Api:
        return cls(httpx.Client(base_url=base_url, timeout=TURN_TIMEOUT_S))

    def run(self, case: dict[str, Any], run_id: str, arm: str) -> dict[str, Any]:
        """One run: seed → one turn per scripted message → FinalState (FR-02)."""
        seeded = self._json(self.http.post("/api/eval/seed", json={
            "initial_state": case["initial_state"], "run_id": run_id, "arm": arm}))
        if seeded.get("mode") != "replay":                   # AC-06, ADR 0020: an evaluation never runs in live mode
            raise HarnessError(f"{run_id}: the seeded session is in mode {seeded.get('mode')!r}, not 'replay'")
        cookie = {"Cookie": f"not_session={seeded['session_id']}"}          # D-019: the same way as a browser
        for message in case["messages"]:
            turn = self.http.post(f"/api/agent/threads/{seeded['thread_id']}/runs/stream", headers=cookie, json={
                "input": {"messages": [{"role": "user", "content": message["text"]}], "language": case["language"]}})
            turn.raise_for_status()
            turn.read()                                      # only to know the turn ended; the reply is never scored
        return self._json(self.http.get(f"/api/eval/final-state/{seeded['session_id']}"))

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        response.raise_for_status()
        return response.json()
