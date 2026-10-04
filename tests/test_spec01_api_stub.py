"""Spec 01 T3: api stub. AC-02 (every route answers with the contract's shape), AC-06 (client ids ignored),
AC-07 (mode stored once, dates from clock.today(mode)), D-013 (customer routes carry no internal fields)."""
from __future__ import annotations

import json

import jsonschema
import pytest
from fastapi.testclient import TestClient

from app import fixtures as fx
from app.main import create_app
from nick_of_time.contracts import (CaseSummary, CaseView, CustomerCaseSummary, CustomerCaseView, CustomerTurn,
                                    FinalState, ProductView, load_schema)

ME = fx.CUSTOMERS[0]["customer_id"]
BEARER = {"Authorization": "Bearer stub"}
FORBIDDEN = ("POL-", "score", "zone", "priority", "tags", "sla_due_at", "customer_id", "handoff", "trace\"")


def login(client: TestClient, customer_id: str = ME, mode: str = "replay") -> str:
    r = client.post("/api/sessions", json={"customer_id": customer_id, "mode": mode})
    assert r.status_code == 201
    sid = r.json()["session_id"]
    assert client.post(f"/api/sessions/{sid}/verify", json={"otp": r.json()["otp_demo"]}).status_code == 200
    return sid


@pytest.fixture
def client():
    with TestClient(create_app(eval_mode=False)) as c:
        yield c


@pytest.fixture
def me(client):
    login(client)
    return client


def test_ac_02_health_and_public_routes(client):
    h = client.get("/api/health").json()
    assert h["contract_version"] == "1.1.0" and h["today"]["replay"] == "2026-06-01"
    customers = client.get("/api/demo/customers").json()
    assert len(customers) == 6 and {"customer_id", "scenario", "language"} <= set(customers[0])
    assert client.get("/api/openapi.json").status_code == 200


def test_ac_02_session_flow_and_error_shape(client):
    assert client.post("/api/sessions", json={"customer_id": "CLI-NOPE"}).json()["code"] == "NOT_FOUND"
    r = client.post("/api/sessions", json={"customer_id": ME})
    assert r.json()["mode"] == "live"                                   # default
    sid = r.json()["session_id"]
    bad = client.post(f"/api/sessions/{sid}/verify", json={"otp": "000000"})
    assert bad.status_code == 401 and set(bad.json()) == {"code", "policy_id", "message"}
    assert client.get("/api/me/cases").json()["code"] == "UNAUTHENTICATED"   # not verified yet
    assert client.post("/api/sessions", json={"customer_id": ME, "mode": "x"}).status_code == 400


def test_ac_02_customer_routes_answer_with_model_valid_bodies(me):
    ProductView.model_validate(me.get("/api/me/products").json()[0])
    CustomerCaseSummary.model_validate(me.get("/api/me/cases").json()[0])
    assert me.get("/api/notifications").json()[0]["delivery_status"] == "delivered"
    assert me.put("/api/me/preferences", json={"language": "pt"}).json()["language"] == "pt"
    assert me.put("/api/me/preferences", json={"language": "fr"}).status_code == 400
    CustomerCaseView.model_validate(me.get(f"/api/cases/{fx.CASE_ID}").json())
    assert me.post(f"/api/cases/{fx.CASE_ID}/info", json={"text": "hola"}).status_code == 201
    r = me.post(f"/api/cases/{fx.CASE_ID}/call-request", json={})
    assert r.status_code == 201 and set(r.json()) == {"event_id", "expected_contact_by"}   # D-008
    assert me.post(f"/api/cases/{fx.CASE_ID}/call-request").status_code == 201             # body is optional
    assert me.post(f"/api/cases/{fx.CASE_ID}/reevaluation", json={"reason": "x"}).status_code == 409
    assert me.post(f"/api/cases/{fx.CASE_ID}/channels/telegram").status_code == 201
    assert me.post(f"/api/cases/{fx.CASE_ID}/channels/email", json={"email": "a@b.co"}).status_code == 202
    assert me.post(f"/api/cases/{fx.CASE_ID}/channels/email", json={"email": "nope"}).status_code == 400
    r = me.get("/api/channels/email/confirm?token=stub-token", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith(f"/case/{fx.CASE_ID}")
    assert me.get("/api/channels/email/confirm?token=old").status_code == 410


def test_ac_02_case_ownership_and_missing(me):
    assert me.get(f"/api/cases/{fx.OTHER_CASE_ID}").status_code == 403
    assert me.get("/api/cases/K-000000").status_code == 404


def test_ac_02_agent_proxy_returns_customer_turns(me):
    assert me.post("/api/agent/threads").status_code == 200
    r = me.post("/api/agent/threads/th-1/runs/stream", json={"input": "hola"})
    assert r.headers["content-type"].startswith("text/event-stream")
    data = [l[6:] for l in r.text.splitlines() if l.startswith("data: ")]
    CustomerTurn.model_validate(json.loads(data[-1]))
    CustomerTurn.model_validate(me.get("/api/agent/threads/th-1/state").json())


def test_d013_customer_routes_never_serialize_internal_fields(me):
    bodies = [me.get(f"/api/cases/{fx.CASE_ID}").text, me.get("/api/me/cases").text, me.get("/api/me/products").text,
              me.get("/api/notifications").text, me.get("/api/agent/threads/th-1/state").text,
              me.post("/api/agent/threads/th-1/runs/stream", json={}).text]
    for body in bodies:
        for word in FORBIDDEN:
            assert word not in body, word
    stripped = set(CaseView.model_fields) - set(CustomerCaseView.model_fields)
    assert {"zone", "priority", "tags", "sla_due_at", "customer_id"} <= stripped


def test_ac_02_console_routes_need_a_token_and_answer_model_valid(client):
    assert client.get("/api/console/cases").json()["code"] == "UNAUTHENTICATED"
    rows = client.get("/api/console/cases", headers=BEARER).json()
    CaseSummary.model_validate(rows[0])
    assert client.get("/api/console/cases?zone=medium", headers=BEARER).json() == []
    d = client.get(f"/api/console/cases/{fx.CASE_ID}", headers=BEARER).json()
    CaseView.model_validate(d["case"])
    jsonschema.validate(d["handoff"], load_schema("handoff.schema.json"))
    assert d["events"] and client.get("/api/console/cases/K-000000", headers=BEARER).status_code == 404
    act = {"case_id": fx.CASE_ID, "actor_id": "x", "action": "take", "idempotency_key": "k1"}
    ok = client.post(f"/api/cases/{fx.CASE_ID}/action", json=act, headers=BEARER)
    assert ok.status_code == 200 and ok.json()["new_status"] == "review"
    close = client.post(f"/api/cases/{fx.CASE_ID}/action", json={**act, "action": "close_case"}, headers=BEARER)
    assert close.status_code == 409
    assert client.post(f"/api/cases/{fx.CASE_ID}/action", json=act).status_code == 401
    assert client.get("/api/console/settings", headers=BEARER).json()["supervised_mode"] is True
    assert client.put("/api/console/settings", json={"supervised_mode": False}, headers=BEARER).json()[
        "supervised_mode"] is False
    assert set(client.post("/api/console/demo/reset", headers=BEARER).json()) == {"demo_transactions", "sample_cases"}


def test_ac_02_webhooks_reject_without_secret(client, monkeypatch):
    assert client.post("/api/telegram/webhook", json={}).status_code == 401
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s")
    ok = client.post("/api/telegram/webhook", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": "s"})
    assert ok.json() == {"ok": True}
    assert client.post("/api/resend/webhook", json={}).status_code == 401
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", "r")
    assert client.post("/api/resend/webhook", json={}, headers={"svix-signature": "v1,x"}).json() == {"ok": True}


def test_ac_06_client_ids_in_the_body_are_ignored(client):
    sid = login(client)
    other = fx.CUSTOMERS[1]["customer_id"]
    client.post(f"/api/cases/{fx.CASE_ID}/info", json={"text": "x", "customer_id": other, "session_id": "S-evil"})
    client.post("/api/agent/threads/th-1/runs/stream", json={"session_id": "S-evil", "customer_id": other})
    run = client.app.state.runs[-1]
    assert run == {"session_id": sid, "arm": None, "customer_id": ME}
    r = client.post("/api/sessions", json={"customer_id": ME, "mode": "replay"})
    sid2 = r.json()["session_id"]
    client.post(f"/api/sessions/{sid2}/verify", json={"otp": "123456", "customer_id": other})
    assert client.app.state.sessions[sid2]["customer_id"] == ME
    # a customer with another id in the body still cannot read the first customer's case
    other_client = TestClient(client.app)
    login(other_client, other)
    assert other_client.get(f"/api/cases/{fx.CASE_ID}", params={"customer_id": ME}).status_code == 403


def test_ac_06_unknown_cookie_is_unauthenticated_not_trusted(client):
    client.cookies.set("not_session", "S-forged0000000000")
    assert client.get("/api/me/cases").status_code == 401


def test_ac_07_mode_is_stored_and_dates_follow_it(client, monkeypatch):
    import datetime as dt
    import app.main as main
    monkeypatch.setattr(main, "today", lambda m: fx.REPLAY_TODAY if m == "replay" else dt.date(2026, 10, 4))
    sid = login(client, mode="replay")
    replay = client.get(f"/api/cases/{fx.CASE_ID}").json()
    assert replay["mode"] == "replay" and replay["deadline_countdown_days"] == 2
    client.put("/api/me/preferences", json={"language": "es", "mode": "live"})        # extra field: not writable
    assert client.app.state.sessions[sid]["mode"] == "replay"
    assert client.get(f"/api/cases/{fx.CASE_ID}").json()["mode"] == "replay"
    other = TestClient(client.app)
    login(other, mode="live")
    live = other.get(f"/api/cases/{fx.CASE_ID}").json()
    assert live["mode"] == "live" and live["deadline_countdown_days"] == (fx.case_view().credit_deadline
                                                                          - dt.date(2026, 10, 4)).days


def test_ac_02_eval_hooks_absent_when_eval_mode_is_off(client):
    assert client.post("/api/eval/seed", json={}).status_code == 404
    assert client.get("/api/eval/final-state/S-x").status_code == 404
    assert not [r for r in client.app.routes if "/api/eval" in getattr(r, "path", "")]


def test_ac_02_eval_hooks_when_on(monkeypatch):
    monkeypatch.setenv("EVAL_MODE", "true")
    from app.main import create_app as make
    with TestClient(make()) as c:
        seed = {"initial_state": {"customer_id": ME, "session": "none"}, "run_id": "EV-0001:S1:1", "arm": "S1"}
        r = c.post("/api/eval/seed", json=seed).json()
        assert r["mode"] == "replay" and r["session_id"]
        FinalState.model_validate(c.get(f"/api/eval/final-state/{r['session_id']}").json())
        c.cookies.set("not_session", r["session_id"])
        assert c.get("/api/me/cases").json()["code"] == "UNAUTHENTICATED"   # none: every tool says no session
        exp = c.post("/api/eval/seed", json={**seed, "initial_state": {"customer_id": ME, "session": "expired"}}).json()
        c.cookies.set("not_session", exp["session_id"])
        assert c.get("/api/me/cases").json()["code"] == "SESSION_EXPIRED"
        assert c.post("/api/eval/seed", json={**seed, "initial_state": {"session": "x"}}).status_code == 400
        assert c.get("/api/eval/final-state/S-unknown").status_code == 404
