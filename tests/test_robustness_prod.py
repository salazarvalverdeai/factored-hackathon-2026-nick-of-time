"""Task PRODRUN: the production scripts (eval/robustness/prod_run.py, prod_loadtest.py) against a fake public api over
httpx.MockTransport: the demo flow (session, OTP, thread, SSE turn), the stop on 429 with no retry, the load test's
numbers and the spend projection gate. Offline: nothing reaches a deployed api or a model."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from eval.robustness import prod_loadtest, prod_run, run


def turn_event(reply: str = "Cuéntame qué cargo no reconoces.", chips=("report_unrecognized", "talk_to_person")) -> str:
    turn = {"reply": reply, "language": "es", "decision": "ask", "guardrails_triggered": [], "mode": "replay",
            "trace_id": "tr-1", "suggestions": [{"id": c, "label": c, "kind": "text"} for c in chips]}
    return f"event: progress\ndata: {json.dumps({'step': 'understand'})}\n\nevent: turn\ndata: {json.dumps(turn)}\n\n"


def fake_api(limit_turns: int | None = None, chips=("report_unrecognized", "talk_to_person")):
    seen = {"turn": 0, "paths": []}

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        seen["paths"].append(path)
        if path == "/api/sessions":
            return httpx.Response(201, json={"session_id": "S-1", "otp_demo": "123456"})
        if path.endswith("/verify"):
            assert json.loads(request.content) == {"otp": "123456"}
            return httpx.Response(200, json={"verified": True}, headers={"set-cookie": "nt_session=S-1; Path=/"})
        if path == "/api/agent/threads":
            return httpx.Response(201, json={"thread_id": "th-1"})
        if path.endswith("/runs/stream"):
            seen["turn"] += 1
            if limit_turns is not None and seen["turn"] > limit_turns:
                return httpx.Response(429, json={"code": "RATE_LIMITED"}, headers={"Retry-After": "60"})
            return httpx.Response(200, text=turn_event(chips=chips), headers={"content-type": "text/event-stream"})
        return httpx.Response(404)
    return handle, seen


def test_prod_run_plays_a_character_through_the_demo_flow():
    handle, seen = fake_api()
    cfg = run.characters()
    out = prod_run.converse("http://api", "other_language", cfg["characters"]["other_language"], cfg["victim"],
                            transport=httpx.MockTransport(handle))
    assert [r["n"] for r in out["turns"]] == [1, 2] and out["violations"] == []
    assert out["turns"][0]["decision"] == "ask" and out["turns"][0]["first_event_ms"] is not None
    assert seen["paths"][:3] == ["/api/sessions", "/api/sessions/S-1/verify", "/api/agent/threads"]


def test_prod_run_stops_on_429_without_retrying():
    handle, seen = fake_api(limit_turns=1)
    cfg = run.characters()
    with pytest.raises(prod_run.Stop, match="429"):
        prod_run.converse("http://api", "manipulative", cfg["characters"]["manipulative"], cfg["victim"],
                          transport=httpx.MockTransport(handle))
    assert seen["turn"] == 2            # the refused turn once, never again


def test_loadtest_measures_turns_and_first_events():
    handle, _ = fake_api()
    load = prod_loadtest.Load("http://api", 3, 2, 0.0, transport=httpx.MockTransport(handle))
    out = asyncio.run(load.run())
    assert out["turns_ok"] == 6 and out["errors"] == 0 and out["rate_limited"] == 0
    assert out["requests"] == {"session": 3, "turn": 9}
    assert out["turn_p50_ms"] is not None and out["first_event_p95_ms"] is not None
    assert out["first_progress_p50_ms"] is not None


def test_loadtest_stops_everyone_on_429_and_counts_degraded_turns():
    handle, _ = fake_api(limit_turns=2, chips=("retry", "talk_to_person"))
    out = asyncio.run(prod_loadtest.Load("http://api", 2, 4, 0.0, transport=httpx.MockTransport(handle)).run())
    assert out["rate_limited"] >= 1 and out["turns_ok"] == 2 and out["degraded_turns"] == 2


def test_loadtest_projection_is_priced_and_aborts_over_budget(monkeypatch, capsys):
    per_turn, total = prod_loadtest.projected_usd(40)
    assert 0 < per_turn < 0.05 and total == pytest.approx(per_turn * 40)
    monkeypatch.setenv("BASE_URL", "http://never-called")
    monkeypatch.setenv("SESSIONS", "10")
    monkeypatch.setenv("TURNS", "4")
    monkeypatch.setenv("BUDGET_USD", "0.0001")
    assert prod_loadtest.main() == 2 and "ABORT" in capsys.readouterr().err
