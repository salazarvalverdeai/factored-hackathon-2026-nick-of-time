"""HTTP side of the harness (spec 10 §6): seed a case, send its scripted messages, read FinalState. No text is read.

A scripted message with a `chip` (D-071, AC-14) is a chip press: the harness reads the suggestions of the last reply's
`turn` event, never its text, and sends that chip the way the web does (apps/web/lib/live.ts): an action chip as
`{"messages": [], "action": ...}`, a text chip as its label. A chip the last reply did not offer cannot be pressed, so
the run fails (AC-09: it stays in every denominator)."""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

import httpx

PRODUCTION_HOSTS = ("nickoftime.salazarvalverdeai.com",)     # docs/infrastructure.md: the harness never runs there
TURN_TIMEOUT_S = 60.0                                        # [assumption] spec 10 §5


class HarnessError(RuntimeError):
    """The run set cannot go on (wrong mode, production host, unsealed held-out). Never recorded as a failed run."""


class ChipNotOffered(RuntimeError):
    """The script presses a chip the last reply did not offer: a failed run, never a stopped set (AC-09)."""


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

    def close(self) -> None:
        self.http.close()

    def run(self, case: dict[str, Any], run_id: str, arm: str) -> dict[str, Any]:
        """One run: seed → one turn per scripted message → FinalState (FR-02)."""
        # `language`: the store-backed api takes a turn's language from the session, so the seed stores it (eval/local)
        seeded = self._json(self.http.post("/api/eval/seed", json={
            "initial_state": case["initial_state"], "run_id": run_id, "arm": arm, "language": case["language"]}))
        if seeded.get("mode") != "replay":                   # AC-06, ADR 0020: an evaluation never runs in live mode
            raise HarnessError(f"{run_id}: the seeded session is in mode {seeded.get('mode')!r}, not 'replay'")
        cookie = {"Cookie": f"not_session={seeded['session_id']}"}          # D-019: the same way as a browser
        offered: list[dict[str, Any]] = []
        for message in case["messages"]:
            turn = self.http.post(f"/api/agent/threads/{seeded['thread_id']}/runs/stream", headers=cookie, json={
                "input": {**turn_input(message, offered), "language": case["language"]}})
            self._ok(turn)
            # the turn ended; only its chips are kept, to press one as the web does (the reply is never scored)
            offered = suggestions(turn.read())
        return self._json(self.http.get(f"/api/eval/final-state/{seeded['session_id']}"))

    @staticmethod
    def _ok(response: httpx.Response) -> None:
        """raise_for_status, with the api's `code` and `message` in the error, so runs.jsonl says why a run failed."""
        if response.is_success:
            return
        try:
            body = response.json()
            detail = f" - {body.get('code')}: {body.get('message')}" if isinstance(body, dict) else ""
        except ValueError:
            detail = ""
        raise httpx.HTTPStatusError(f"{response.status_code} {response.request.method} {response.request.url.path}"
                                    f"{detail}", request=response.request, response=response)

    @classmethod
    def _json(cls, response: httpx.Response) -> dict[str, Any]:
        cls._ok(response)
        return response.json()


def turn_input(message: dict[str, Any], offered: list[dict[str, Any]]) -> dict[str, Any]:
    """The run input of one scripted message: typed text, or the press of chip `message["chip"]` among the chips the
    last reply `offered`, sent as apps/web/lib/live.ts sends it (spec 04 AC-32, spec 10 AC-14)."""
    if not message.get("chip"):
        return {"messages": [{"role": "user", "content": message["text"]}]}
    chip = next((item for item in offered if item.get("id") == message["chip"]), None)
    if chip is None or chip.get("kind") == "link":
        raise ChipNotOffered(f"the last reply did not offer the chip {message['chip']!r} "
                             f"(offered: {[item.get('id') for item in offered]})")
    if chip.get("kind") == "action":
        return {"messages": [], "action": chip["action"]}
    return {"messages": [{"role": "user", "content": chip["label"]}]}


def suggestions(body: bytes) -> list[dict[str, Any]]:
    """The chips of the last `turn` event of an SSE body (`event:` then one `data:` JSON line); [] when there is none."""
    chips: list[dict[str, Any]] = []
    for block in body.decode("utf-8", "replace").replace("\r\n", "\n").split("\n\n"):
        lines = block.split("\n")
        if "event: turn" not in lines:
            continue
        try:
            turn = json.loads("".join(line[len("data:"):].strip() for line in lines if line.startswith("data:")))
        except ValueError:
            continue
        chips = (turn.get("suggestions") or []) if isinstance(turn, dict) else []
    return chips
