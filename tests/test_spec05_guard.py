"""Spec 05 AC-18: the public abuse guard (per-IP and global hourly limits, the client IP only from the trusted proxy) and
the api side of the G-OPS-01 daily LLM cap (each turn's usage written once to `llm_calls`, never a stale or failed
run's; the day's sum in the run's configurable). Offline: MemoryStore, the fake Platform of the spec 05 suite."""
from __future__ import annotations

import datetime as dt
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import fixtures as fx
from app.guard import MESSAGE
from app.main import COOKIE, create_app
from app.platform import HttpPlatform, PlatformError
from tests.test_spec05_api import HTTPS, ME, SECRET, Env

CADDY = ("172.18.0.5", 40000)      # a peer on the compose network
STRANGER = ("203.0.113.9", 40000)  # any other peer
USAGE = {"provider": "bedrock", "model": "claude-haiku-4-5", "tokens_in": 300, "tokens_out": 60, "latency_ms": 900,
         "cost_usd": 0.0015}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
    monkeypatch.delenv("DAILY_LLM_CAP_USD", raising=False)
    return Env()


def client(env: Env, peer=CADDY) -> TestClient:
    return TestClient(env.app, base_url=HTTPS, client=peer)


def new_session(c: TestClient, ip: str | None = None):
    return c.post("/api/sessions", json={"customer_id": ME, "mode": "replay"},
                  headers={"X-Forwarded-For": ip} if ip else {})


def billed(trace: str) -> dict:
    return {**fx.turn_result().model_dump(mode="json"), "trace_id": trace, "usage": [USAGE, USAGE]}


def stream(env: Env, browser: TestClient | None = None) -> str:
    browser = browser or env.client
    thread = browser.post("/api/agent/threads").json()["thread_id"] if browser is env.client else "T-1"
    return browser.post(f"/api/agent/threads/{thread}/runs/stream", json={}).text


# ---------- the guard ----------
def test_ac_18_sessions_are_limited_per_forwarded_ip_with_a_calm_es_pt_429(env):
    via = client(env)
    assert [new_session(via, "198.51.100.1").status_code for _ in range(10)] == [201] * 10
    refused = new_session(via, "198.51.100.1")
    assert refused.status_code == 429 and int(refused.headers["Retry-After"]) > 0
    assert refused.json() == {"code": "RATE_LIMITED", "policy_id": None, "message": MESSAGE}
    assert "Intenta de nuevo" in MESSAGE and "Tente novamente" in MESSAGE
    assert new_session(via, "198.51.100.2").status_code == 201                      # another client is unaffected


def test_ac_18_x_forwarded_for_from_a_non_proxy_peer_is_ignored(env):
    direct = client(env, STRANGER)
    codes = [new_session(direct, f"198.51.100.{i}").status_code for i in range(11)]  # spoofed, a new value each time
    assert codes == [201] * 10 + [429]                                               # all counted as the peer
    assert new_session(client(env), "203.0.113.9").status_code == 429               # the same IP behind Caddy
    assert new_session(client(env), "198.51.100.1").status_code == 201             # a spoofed value never counted


def test_ac_18_an_ipv6_client_is_counted_by_its_64(env):
    via = client(env)
    codes = [new_session(via, f"2001:db8:1:2::{i:x}").status_code for i in range(11)]
    assert codes == [201] * 10 + [429] and new_session(via, "2001:db8:1:3::1").status_code == 201


def test_ac_18_the_window_resets_after_an_hour(env):
    via = client(env)
    for _ in range(10):
        new_session(via, "198.51.100.1")
    env.clock["t"] += dt.timedelta(minutes=59)
    assert new_session(via, "198.51.100.1").status_code == 429
    env.clock["t"] += dt.timedelta(minutes=1, seconds=1)
    assert new_session(via, "198.51.100.1").status_code == 201


def test_ac_18_the_global_ceiling_stops_many_ips(env):
    env.app.state.limiter.limits["session"] = (10, 3)
    via = client(env)
    assert [new_session(via, f"198.51.100.{i}").status_code for i in range(4)] == [201, 201, 201, 429]


def test_ac_18_agent_turns_are_limited_per_ip_and_other_routes_are_not(env):
    env.app.state.limiter.limits["turn"] = (3, 100)
    via, ip = client(env), {"X-Forwarded-For": "198.51.100.1"}
    created = new_session(via, "198.51.100.1").json()
    via.post(f"/api/sessions/{created['session_id']}/verify", json={"otp": created["otp_demo"]})
    thread = via.post("/api/agent/threads", headers=ip).json()["thread_id"]
    run = f"/api/agent/threads/{thread}/runs/stream"
    assert [via.post(run, json={}, headers=ip).status_code for _ in range(3)] == [200, 200, 429]   # thread = 1st hit
    assert all(via.get("/api/me/cases", headers=ip).status_code == 200 for _ in range(5))


# ---------- usage and the daily cap ----------
def test_ac_18_each_trace_is_written_once_and_the_next_run_carries_the_day_spend(env):
    env.platform.turn = billed("tr-1")
    env.login()
    stream(env)
    first = env.platform.calls[-1][0]
    assert first["llm_day_spent_usd"] == 0 and first["llm_day_cap_usd"] == 5.0
    stream(env)                                                                     # the same trace streamed again
    rows = env.store.list_llm_calls(run_id=None)
    assert len(rows) == 2 and {r.trace_id for r in rows} == {"tr-1"} and rows[0].model == "claude-haiku-4-5"
    assert env.platform.calls[-1][0]["llm_day_spent_usd"] == pytest.approx(0.003)
    env.clock["t"] += dt.timedelta(days=1)                                          # a new UTC day starts at 0
    env.login()
    stream(env)
    assert env.platform.calls[-1][0]["llm_day_spent_usd"] == 0


def test_ac_18_the_daily_cap_is_read_from_the_environment_at_start(monkeypatch):
    monkeypatch.setenv("DAILY_LLM_CAP_USD", "1.5")
    env = Env()
    monkeypatch.setenv("DAILY_LLM_CAP_USD", "9")                                     # later changes need a restart
    env.login()
    stream(env)
    assert env.platform.calls[-1][0]["llm_day_cap_usd"] == 1.5


class Dropping:
    """A fake Platform whose stream fails after the run billed a call; its state holds that run's turn."""

    def __init__(self, base, turn):
        self.base, self.turn = base, turn

    def __getattr__(self, name):
        return getattr(self.base, name)

    def stream(self, thread_id, configurable, payload):
        yield "progress", {"step": "x", "label": "x", "state": "in_progress", "at": "2026-06-01T15:00:00+00:00"}
        raise PlatformError("reset")

    def state(self, thread_id):
        return self.turn


def test_ac_18_a_stream_without_a_turn_logs_the_runs_usage_from_the_thread_state_once(env):
    sid = env.login()
    thread = env.client.post("/api/agent/threads").json()["thread_id"]
    app = create_app(store=env.store, platform=Dropping(env.platform, billed("tr-late")), notifier=env.notifier,
                     now=lambda: env.clock["t"])
    with TestClient(app, base_url=HTTPS) as browser:
        browser.cookies.set(COOKIE, sid)
        for _ in range(2):
            text = browser.post(f"/api/agent/threads/{thread}/runs/stream", json={}).text
            assert fx.MESSAGES["system"]["agent_unavailable"]["es"] in json.loads(
                text.split("event: turn\ndata: ")[1].split("\n")[0])["reply"]
    assert [r.trace_id for r in env.store.list_llm_calls(run_id=None)] == ["tr-late", "tr-late"]   # 2 rows, not 4


def _sse(*parts) -> str:
    return "".join(f"event: {e}\ndata: {d if isinstance(d, str) else json.dumps(d)}\n\n" for e, d in parts)


@pytest.mark.parametrize("body", [
    _sse(("values", billed("tr-old")), ("error", {"error": "ValueError", "message": "language must be es"})),
    _sse(("values", billed("tr-old"))),                                             # only the pre-run state
], ids=["error-event", "stale-only"])
def test_ac_18_a_platform_error_or_the_previous_state_is_neither_logged_nor_the_turn(env, body):
    env.platform.turn = billed("tr-old")
    sid = env.login()
    stream(env)                                                                     # the previous run, logged

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/threads/T-1":
            return httpx.Response(200, json={"metadata": {"session_id": sid}})
        if request.url.path.endswith("/state"):
            return httpx.Response(200, json={"values": billed("tr-old")})
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    app = create_app(store=env.store, platform=HttpPlatform("https://p.example", "k",
                                                            transport=httpx.MockTransport(handler)),
                     notifier=env.notifier, now=lambda: env.clock["t"])
    with TestClient(app, base_url=HTTPS) as browser:
        browser.cookies.set(COOKIE, sid)
        text = stream(env, browser)
    turn = json.loads(text.split("event: turn\ndata: ")[1].split("\n")[0])
    assert turn["trace_id"] != "tr-old" and turn["reply"] == fx.MESSAGES["system"]["agent_unavailable"]["es"]
    assert len(env.store.list_llm_calls(run_id=None)) == 2                          # still only the previous run's


def test_ac_18_a_fresh_final_state_after_the_pre_run_state_is_the_turn_and_is_logged(env):
    body = _sse(("values", billed("tr-old")), ("values", billed("tr-new")))
    sid = env.login()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/threads/T-1":
            return httpx.Response(200, json={"metadata": {"session_id": sid}})
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    platform = HttpPlatform("https://p.example", "k", transport=httpx.MockTransport(handler))
    app = create_app(store=env.store, platform=platform, notifier=env.notifier, now=lambda: env.clock["t"])
    with TestClient(app, base_url=HTTPS) as browser:
        browser.cookies.set(COOKIE, sid)
        text = stream(env, browser)
    assert json.loads(text.split("event: turn\ndata: ")[1].split("\n")[0])["trace_id"] == "tr-new"
    assert [r.trace_id for r in env.store.list_llm_calls(run_id=None)] == ["tr-new", "tr-new"]
