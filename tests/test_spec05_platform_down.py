"""Spec 05 AC-05: Platform (a free preemptible deployment) down, slow, erroring or dropping the stream gives the
customer a normal `turn` with a calm retry message, never a raw 503 or an `error` event."""
from __future__ import annotations

import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app import fixtures as fx
from app.main import create_app
from app.platform import HttpPlatform
from tests.test_spec05_api import HTTPS, SECRET, START, Env



@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    return Env()


PROGRESS = {"step": "block_card", "label": "x", "state": "in_progress", "at": START.isoformat()}


def _sse(*parts) -> str:
    return "".join(f"event: {e}\ndata: {json.dumps(d)}\n\n" for e, d in parts)


def _platform(env, run):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/threads/T-1":
            return httpx.Response(200, json={"metadata": {"session_id": env.sid}})
        return run(request)
    return HttpPlatform("https://platform.internal.example", "k", transport=httpx.MockTransport(handler))


def _boom(request):
    raise httpx.ConnectError("refused https://platform.internal.example")


def _timeout(request):
    raise httpx.ReadTimeout("slow")


def _drop(request):             # one progress event, then the connection dies mid-body
    class Dying(httpx.SyncByteStream):
        def __iter__(self):
            yield _sse(("custom", PROGRESS)).encode()
            raise httpx.ReadError("reset")
    return httpx.Response(200, stream=Dying(), headers={"content-type": "text/event-stream"})


@pytest.mark.parametrize("run, progress", [
    (_boom, 0), (_timeout, 0), (lambda r: httpx.Response(503, text="Traceback ..."), 0), (_drop, 1),
    (lambda r: httpx.Response(200, text=_sse(("custom", PROGRESS))), 1),          # ends with no turn
    (lambda r: httpx.Response(200, text="event: values\ndata: {not json\n\n"), 0),
], ids=["unreachable", "timeout", "5xx", "dropped", "no-turn", "garbage"])
def test_ac_05_platform_failure_is_a_calm_turn(env, caplog, run, progress):
    env.sid = env.login()
    app = create_app(store=env.store, platform=_platform(env, run), notifier=env.notifier, now=lambda: env.clock["t"])
    with TestClient(app, base_url=HTTPS) as browser, caplog.at_level(logging.ERROR, "nick_of_time.api"):
        browser.cookies.set("not_session", env.sid)
        r = browser.post("/api/agent/threads/T-1/runs/stream", json={})
    assert r.status_code == 200 and "event: error" not in r.text
    assert r.text.count("event: progress") == progress and r.text.count("event: turn") == 1
    turn = json.loads(r.text.split("event: turn\ndata: ")[1].split("\n")[0])
    assert turn["reply"] == fx.MESSAGES["system"]["agent_unavailable"][turn["language"]]
    assert [c["id"] for c in turn["suggestions"]] == ["retry", "talk_to_person"]
    assert not any(x in r.text for x in ("platform.internal", "Traceback", "refused", "T-1"))
    assert turn["trace_id"] in caplog.text                       # logged server-side with the same trace id


def test_ac_05_platform_down_before_the_run_is_also_a_turn(env):
    env.sid = env.login()
    app = create_app(store=env.store, platform=_platform(env, _boom), notifier=env.notifier, now=lambda: env.clock["t"])
    with TestClient(app, base_url=HTTPS) as browser:
        browser.cookies.set("not_session", env.sid)
        r = browser.post("/api/agent/threads/T-2/runs/stream", json={})      # thread check hits the same dead host
    assert r.status_code == 200 and r.text.startswith("event: turn")
