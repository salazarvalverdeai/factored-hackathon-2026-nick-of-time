"""Spec 01 T3: api stub. AC-02 (every route answers with the contract's shape), AC-06 (client ids ignored),
AC-07 (mode stored once, dates from clock.today(mode, country)), D-013 (customer routes carry no internal fields)."""
from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

import jsonschema
import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

import app.main as main
from app import fixtures as fx
from app.main import create_app
from nick_of_time.contracts import (CaseView, CustomerCaseSummary, CustomerCaseView, CustomerTurn, ProductView,
                                    ProgressItem, FinalState, load_schema)

ME = fx.CUSTOMERS[0]["customer_id"]
OTHER = fx.CUSTOMERS[1]["customer_id"]
BEARER = {"Authorization": "Bearer stub"}
HTTPS = "https://testserver"
FORBIDDEN = ("POL-", "score", "zone", "priority", "tags", "sla_due_at", "customer_id", "handoff", "trace\"")
ACTION = {"case_id": fx.CASE_ID, "actor_id": "x", "action": "take", "idempotency_key": "k1"}
SEED = {"initial_state": {"customer_id": ME, "session": "verified"}, "run_id": "EV-0001:S1:1", "arm": "S1"}


def new_client(app=None) -> TestClient:
    return TestClient(app or create_app(eval_mode=False), base_url=HTTPS)


def login(client: TestClient, customer_id: str = ME, mode: str = "replay") -> str:
    r = client.post("/api/sessions", json={"customer_id": customer_id, "mode": mode})
    assert r.status_code == 201
    sid = r.json()["session_id"]
    assert client.post(f"/api/sessions/{sid}/verify", json={"otp": r.json()["otp_demo"]}).status_code == 200
    return sid


@pytest.fixture
def client():
    with new_client() as c:
        yield c


@pytest.fixture
def me(client):
    login(client)
    return client


# ---- AC-02: ONE table over spec 01 §6.2 and §6.8 -------------------------------------------------------------------
# (method, path, auth, body, status, model, case) — `case` fills {case_id}; model None = no JSON model (stream, 302).
RES, OWN = fx.RESOLVED_CASE_ID, fx.CASE_ID
LIST = TypeAdapter
ROWS = [
    ("GET", "/api/health", "public", None, 200, main.HealthOut, OWN),
    ("GET", "/api/demo/customers", "public", None, 200, LIST(list[main.DemoCustomerOut]), OWN),
    ("POST", "/api/sessions", "public", {"customer_id": ME, "mode": "replay"}, 201, main.SessionOut, OWN),
    ("POST", "/api/sessions/{session_id}/verify", "public", {"otp": fx.OTP}, 200, main.VerifyOut, OWN),
    ("POST", "/api/agent/threads", "known", None, 200, main.ThreadOut, OWN),
    ("POST", "/api/agent/threads/{thread_id}/runs/stream", "known", {"input": "hola"}, 200, None, OWN),
    ("GET", "/api/agent/threads/{thread_id}/state", "known", None, 200, CustomerTurn, OWN),
    ("GET", "/api/notifications", "customer", None, 200, LIST(list[main.NotificationOut]), OWN),
    ("GET", "/api/me/products", "customer", None, 200, LIST(list[ProductView]), OWN),
    ("GET", "/api/me/cases", "customer", None, 200, LIST(list[CustomerCaseSummary]), OWN),
    ("PUT", "/api/me/preferences", "customer", {"language": "pt"}, 200, main.PrefsOut, OWN),
    ("GET", "/api/cases/{case_id}", "customer", None, 200, CustomerCaseView, OWN),
    ("POST", "/api/cases/{case_id}/info", "customer", {"text": "hola"}, 201, main.EventOut, OWN),
    ("POST", "/api/cases/{case_id}/call-request", "customer", {}, 201, main.CallOut, OWN),
    ("POST", "/api/cases/{case_id}/reevaluation", "customer", {"reason": "x"}, 201, main.ReevalOut, RES),
    ("POST", "/api/cases/{case_id}/channels/telegram", "customer", None, 201, main.TelegramOut, OWN),
    ("POST", "/api/cases/{case_id}/channels/email", "customer", {"email": "a@b.co"}, 202, main.EmailOut, OWN),
    ("GET", "/api/channels/email/confirm?token=stub-token", "public", None, 302, None, OWN),
    ("POST", "/api/telegram/webhook", "webhook", {}, 200, main.AckOut, OWN),
    ("POST", "/api/resend/webhook", "webhook", {}, 200, main.AckOut, OWN),
    ("GET", "/api/console/cases", "analyst", None, 200, LIST(list[main.CaseSummary]), OWN),
    ("GET", "/api/console/cases/{case_id}", "analyst", None, 200, main.ConsoleCaseOut, OWN),
    ("POST", "/api/cases/{case_id}/action", "analyst", ACTION, 200, main.AnalystActionOut, OWN),
    ("POST", "/api/cases/{case_id}/action", "analyst", {**ACTION, "case_id": RES, "action": "close_case"}, 200,
     main.AnalystActionOut, RES),
    ("GET", "/api/console/settings", "analyst", None, 200, main.SettingsOut, OWN),
    ("PUT", "/api/console/settings", "analyst", {"supervised_mode": False}, 200, main.SettingsOut, OWN),
    ("POST", "/api/console/demo/reset", "analyst", None, 200, main.ResetOut, OWN),
    ("POST", "/api/eval/seed", "eval", SEED, 200, main.SeedOut, OWN),
    ("GET", "/api/eval/final-state/{session_id}", "eval", None, 200, FinalState, OWN),
]
DOCS = {"/api/docs", "/api/openapi.json"}
# AC-02: the exact key set of each dict-shaped response, typed out from spec 01 §6.2 / §6.8 (not read from the models).
KEYS = {
    main.HealthOut: "status version contract_version git_sha gold_version policies_version platform_revision models "
                    "prompt_hash classifier_version today",
    main.SessionOut: "session_id mode today otp_demo expires_at", main.VerifyOut: "verified expires_at",
    main.ThreadOut: "thread_id", main.PrefsOut: "display_currency language", main.EventOut: "event_id",
    main.CallOut: "event_id expected_contact_by", main.ReevalOut: "event_id case_id",
    main.TelegramOut: "deep_link expires_at", main.EmailOut: "confirmation_sent", main.AckOut: "ok",
    main.SettingsOut: "supervised_mode score_provider policies_version",
    main.ResetOut: "demo_transactions sample_cases", main.SeedOut: "session_id thread_id run_id arm mode",
    main.DemoCustomerOut: "customer_id display_name country segment scenario language",
    main.NotificationOut: "notification_id case_id event channel masked_address text delivery_status created_at",
}
LIST_ROWS = {"/api/demo/customers": main.DemoCustomerOut, "/api/notifications": main.NotificationOut}


def _call(c, row, sid, tid, path_case=None, headers=None, cookies=True):
    method, path, _, body, *_rest = row
    path = path.format(case_id=path_case or row[6], session_id=sid, thread_id=tid)
    kw = {"headers": headers or {}, "follow_redirects": False}
    if body is not None:
        kw["json"] = body
    return c.request(method, path, **kw)


def _prepared(monkeypatch, row):
    """A fresh app with EVAL on; a verified session, one thread, the webhook secrets; the row's own auth headers."""
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s")
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", "r")
    c = new_client(create_app(eval_mode=True))
    auth = row[2]
    if row[1].endswith("/verify"):
        sid = c.post("/api/sessions", json={"customer_id": ME, "mode": "replay"}).json()["session_id"]
    else:
        sid = login(c)
    if row[1].startswith("/api/eval/final"):
        sid = c.post("/api/eval/seed", json=SEED).json()["session_id"]
    tid = c.post("/api/agent/threads").json().get("thread_id")      # none for the unverified verify row
    headers = {"analyst": BEARER, "eval": {}, "webhook": {"X-Telegram-Bot-Api-Secret-Token": "s",
                                                           "svix-signature": "v1,x"}}.get(auth, {})
    return c, sid, tid, headers


def test_ac_02_app_routes_equal_the_table():
    app = create_app(eval_mode=True)
    in_app = {(m, r.path) for r in app.routes for m in getattr(r, "methods", ()) if m not in ("HEAD", "OPTIONS")}
    in_app = {(m, p) for m, p in in_app if p not in DOCS}
    in_table = {(row[0], row[1].split("?")[0]) for row in ROWS}
    assert in_app == in_table


@pytest.mark.parametrize("row", ROWS, ids=lambda r: f"{r[0]} {r[1]} {r[6]}")
def test_ac_02_every_row_returns_its_status_and_a_model_valid_body(monkeypatch, row):
    c, sid, tid, headers = _prepared(monkeypatch, row)
    r = _call(c, row, sid, tid, headers=headers)
    assert r.status_code == row[4], r.text
    model = row[5]
    if model is not None:
        (model.validate_python if isinstance(model, TypeAdapter) else model.model_validate)(r.json())
    if row[1].startswith("/api/agent/threads/{thread_id}/runs"):
        assert r.headers["content-type"].startswith("text/event-stream")


@pytest.mark.parametrize("row", [r for r in ROWS if r[5] in KEYS or r[1] in LIST_ROWS],
                         ids=lambda r: f"{r[0]} {r[1]}")
def test_ac_02_response_key_sets_are_exactly_the_spec(monkeypatch, row):
    """AC-02: a field dropped from both the model and the route, or an extra one, fails here."""
    c, sid, tid, headers = _prepared(monkeypatch, row)
    body = _call(c, row, sid, tid, headers=headers).json()
    model = LIST_ROWS.get(row[1]) or row[5]
    if row[1] in LIST_ROWS:
        body = body[0]
    keys = set(KEYS[model].split())
    assert set(body) == keys and set(model.model_fields) == keys


@pytest.mark.parametrize("row", [r for r in ROWS if r[2] in ("customer", "known")],
                         ids=lambda r: f"{r[0]} {r[1]}")
def test_ac_02_customer_rows_without_a_cookie_are_401(monkeypatch, row):
    c, sid, tid, _ = _prepared(monkeypatch, row)
    c.cookies.clear()
    r = _call(c, row, sid, tid)
    assert r.status_code == 401 and r.json()["code"] == "UNAUTHENTICATED" and r.json()["policy_id"] is None


@pytest.mark.parametrize("row", [r for r in ROWS if r[2] == "analyst"], ids=lambda r: f"{r[0]} {r[1]}")
def test_ac_02_analyst_rows_without_a_bearer_are_401(monkeypatch, row):
    c, sid, tid, _ = _prepared(monkeypatch, row)
    assert _call(c, row, sid, tid).status_code == 401


@pytest.mark.parametrize("row", [r for r in ROWS if r[2] == "customer" and "{case_id}" in r[1]],
                         ids=lambda r: f"{r[0]} {r[1]}")
def test_ac_02_case_rows_on_another_customers_case_are_403(monkeypatch, row):
    c, sid, tid, _ = _prepared(monkeypatch, row)
    r = _call(c, row, sid, tid, path_case=fx.OTHER_CASE_ID)
    assert r.status_code == 403 and r.json()["policy_id"] is None
    assert c.app.state.policy_denials[-1]["policy_id"] == "POL-CROSS-CUSTOMER"      # kept server-side


@pytest.mark.parametrize("row", [r for r in ROWS if r[2] == "webhook"], ids=lambda r: r[1])
def test_ac_02_webhooks_reject_a_wrong_or_missing_secret(monkeypatch, row):
    c, sid, tid, _ = _prepared(monkeypatch, row)
    assert _call(c, row, sid, tid).status_code == 401
    assert _call(c, row, sid, tid, headers={"X-Telegram-Bot-Api-Secret-Token": "bad"}).status_code == 401
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET")
    monkeypatch.delenv("RESEND_WEBHOOK_SECRET")
    assert _call(c, row, sid, tid, headers={"X-Telegram-Bot-Api-Secret-Token": "s", "svix-signature": "v1,x"}
                 ).status_code == 401


# ---- error shapes and the remaining paths ---------------------------------------------------------------------------
def test_ac_02_session_flow_and_error_shape(client):
    assert client.post("/api/sessions", json={"customer_id": "CLI-NOPE"}).json()["code"] == "NOT_FOUND"
    r = client.post("/api/sessions", json={"customer_id": ME})
    assert r.json()["mode"] == "live"
    sid = r.json()["session_id"]
    bad = client.post(f"/api/sessions/{sid}/verify", json={"otp": "000000"})
    assert bad.status_code == 401 and set(bad.json()) == {"code", "policy_id", "message"}
    assert client.get("/api/me/cases").json()["code"] == "UNAUTHENTICATED"
    assert client.post("/api/sessions", json={"customer_id": ME, "mode": "x"}).status_code == 400
    assert client.put("/api/me/preferences", json={"language": "fr"}).status_code in (400, 401)


def test_ac_02_misc_error_paths(me):
    assert me.get("/api/cases/K-000000").status_code == 404
    assert me.post(f"/api/cases/{fx.CASE_ID}/channels/email", json={"email": "nope"}).status_code == 400
    assert me.post(f"/api/cases/{fx.CASE_ID}/call-request").status_code == 201              # body is optional
    old = me.get("/api/channels/email/confirm?token=old")
    assert old.status_code == 410 and old.json()["code"] != "NOT_FOUND"
    close = me.post(f"/api/cases/{fx.CASE_ID}/action", json={**ACTION, "action": "close_case"}, headers=BEARER)
    assert close.status_code == 409 and close.json()["policy_id"] == "case_queue.transitions"   # analyst keeps it


def test_ac_02_session_cookie_ttl_and_flags(client):
    r = client.post("/api/sessions", json={"customer_id": ME})
    sid = r.json()["session_id"]
    ttl = fx.POLICIES["identity"]["session_ttl_minutes"]
    assert ttl == 15
    exp = dt.datetime.fromisoformat(r.json()["expires_at"]) - dt.datetime.now(dt.timezone.utc)
    assert dt.timedelta(minutes=ttl - 1) < exp <= dt.timedelta(minutes=ttl)
    cookie = client.post(f"/api/sessions/{sid}/verify", json={"otp": fx.OTP}).headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie and f"max-age={ttl * 60}" in cookie


def test_ac_02_health_reads_versions_from_the_contract_and_policies(client):
    from nick_of_time import CONTRACT_VERSION
    h = client.get("/api/health").json()
    assert h["contract_version"] == CONTRACT_VERSION and h["policies_version"] == fx.POLICIES["version"]
    assert h["today"]["replay"] == "2026-06-01"


def test_ac_02_a_verified_session_expires(me):
    sid = next(iter(me.app.state.sessions))
    me.app.state.sessions[sid]["expires_at"] = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
    r = me.get("/api/me/cases")
    assert r.status_code == 401 and r.json()["code"] == "SESSION_EXPIRED"


# ---- agent proxy ---------------------------------------------------------------------------------------------------
def _events(text: str) -> list[tuple[str, dict]]:
    out, ev = [], None
    for line in text.splitlines():
        if line.startswith("event: "):
            ev = line[7:]
        elif line.startswith("data: "):
            out.append((ev, json.loads(line[6:])))
    return out


def test_ac_02_stream_events_are_valid_progress_and_customer_turns(me):
    tid = me.post("/api/agent/threads").json()["thread_id"]
    events = _events(me.post(f"/api/agent/threads/{tid}/runs/stream", json={"input": "hola"}).text)
    assert [e for e, _ in events] == ["progress", "turn"]
    for ev, data in events:
        {"progress": ProgressItem, "turn": CustomerTurn}[ev].model_validate(data)


def test_ac_06_threads_are_bound_to_their_session(client):
    login(client)
    tid = client.post("/api/agent/threads").json()["thread_id"]
    assert len(tid) == 36                                               # a UUID, like LangGraph thread ids
    second = new_client(client.app)
    login(second, OTHER)
    for r in (second.get(f"/api/agent/threads/{tid}/state"),
              second.post(f"/api/agent/threads/{tid}/runs/stream", json={})):
        assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"
    assert client.get("/api/agent/threads/00000000-0000-0000-0000-000000000000/state").status_code == 404
    assert client.get(f"/api/agent/threads/{tid}/state").status_code == 200


def test_ac_07_agent_routes_forward_expired_and_unverified_sessions(client):
    client.cookies.set("not_session", "S-forged0000000000")
    assert client.post("/api/agent/threads").status_code == 401                        # unknown cookie
    unverified = client.post("/api/sessions", json={"customer_id": ME, "mode": "replay"}).json()["session_id"]
    client.cookies.set("not_session", unverified)
    tid = client.post("/api/agent/threads").json()["thread_id"]
    r = client.post(f"/api/agent/threads/{tid}/runs/stream", json={})
    assert r.status_code == 200 and client.app.state.runs[-1]["session_state"] == "unverified"
    assert _events(r.text)[-1][1]["decision"] == "reauthenticate"
    client.cookies.clear()
    sid = login(client)
    client.app.state.sessions[sid]["expires_at"] = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
    tid = client.post("/api/agent/threads").json()["thread_id"]
    assert client.post(f"/api/agent/threads/{tid}/runs/stream", json={}).status_code == 200
    assert client.app.state.runs[-1]["session_state"] == "expired"
    assert client.get("/api/me/cases").json()["code"] == "SESSION_EXPIRED"            # data routes keep 401


def _expire(c, sid):
    c.app.state.sessions[sid]["expires_at"] = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)


def test_ac_07_state_on_an_expired_session_is_401_and_not_forwarded(client):
    """AC-07 / G-SES-01 (expired -> no data): GET state is not forwarded; it answers 401 SESSION_EXPIRED."""
    sid = login(client)
    tid = client.post("/api/agent/threads").json()["thread_id"]
    runs = len(client.app.state.runs)
    _expire(client, sid)
    r = client.get(f"/api/agent/threads/{tid}/state")
    assert r.status_code == 401 and r.json() == {"code": "SESSION_EXPIRED", "policy_id": None,
                                                 "message": "Session expired: verify again"}
    assert len(client.app.state.runs) == runs and "K-" not in r.text


def test_ac_07_reauthenticate_reply_carries_no_data(client):
    """AC-07 / G-SES-01: an expired session's turn has no case id, receipt or action claim, only the session line."""
    sid = login(client)
    tid = client.post("/api/agent/threads").json()["thread_id"]
    _expire(client, sid)
    r = client.post(f"/api/agent/threads/{tid}/runs/stream", json={"input": "hola"})
    events = _events(r.text)
    assert [e for e, _ in events] == ["turn"]                          # no progress event: nothing was done
    turn = CustomerTurn.model_validate(events[0][1])
    assert turn.decision == "reauthenticate" and turn.case_id is None and turn.receipt is None
    assert "K-" not in turn.reply and "bloque" not in turn.reply.lower()
    assert turn.reply == fx.MESSAGES["connect"]["general_contact"]["es"]
    assert [s.label for s in turn.suggestions] == [fx.MESSAGES["suggest"]["reauthenticate"]["es"],
                                             fx.MESSAGES["suggest"]["request_call"]["es"]]
    assert set(events[0][1]) == set(CustomerTurn.model_fields)


# ---- privacy -------------------------------------------------------------------------------------------------------
def test_privacy_notifications_and_products_follow_the_sessions_customer(me):
    assert me.get("/api/notifications").json() and me.get("/api/me/products").json()
    other = new_client(me.app)
    login(other, OTHER)
    assert other.get("/api/notifications").json() == []
    assert other.get("/api/me/products").json() == []
    assert other.get("/api/me/cases").json() == []


def test_d013_customer_routes_never_serialize_internal_fields(me):
    tid = me.post("/api/agent/threads").json()["thread_id"]
    anon = new_client(me.app)
    bodies = [me.get(f"/api/cases/{fx.CASE_ID}").text, me.get("/api/me/cases").text, me.get("/api/me/products").text,
              me.get("/api/notifications").text, me.get(f"/api/agent/threads/{tid}/state").text,
              me.post(f"/api/agent/threads/{tid}/runs/stream", json={}).text,
              anon.get("/api/me/cases").text,                                                     # 401
              me.get(f"/api/cases/{fx.OTHER_CASE_ID}").text,                                      # 403
              me.post(f"/api/cases/{fx.CASE_ID}/reevaluation", json={"reason": "x"}).text]       # 409
    assert me.post(f"/api/cases/{fx.CASE_ID}/reevaluation", json={"reason": "x"}).status_code == 409
    for body in bodies:
        for word in FORBIDDEN:
            assert word not in body, word
    stripped = set(CaseView.model_fields) - set(CustomerCaseView.model_fields)
    assert {"zone", "priority", "tags", "sla_due_at", "customer_id"} <= stripped


def test_ac_06_client_ids_in_the_body_are_ignored(client):
    sid = login(client)
    tid = client.post("/api/agent/threads").json()["thread_id"]
    client.post(f"/api/cases/{fx.CASE_ID}/info", json={"text": "x", "customer_id": OTHER, "session_id": "S-evil"})
    evil = {"session_id": "S-evil", "customer_id": OTHER,
            "config": {"configurable": {"session_id": "S-evil", "customer_id": OTHER, "mode": "live"}}}
    client.post(f"/api/agent/threads/{tid}/runs/stream", json=evil)
    run = client.app.state.runs[-1]
    assert run == {"session_id": sid, "session_state": "verified", "mode": "replay", "arm": None, "case_id": None}
    assert "customer_id" not in run
    sid2 = client.post("/api/sessions", json={"customer_id": ME, "mode": "replay"}).json()["session_id"]
    client.post(f"/api/sessions/{sid2}/verify", json={"otp": fx.OTP, "customer_id": OTHER})
    assert client.app.state.sessions[sid2]["customer_id"] == ME
    other_client = new_client(client.app)
    login(other_client, OTHER)
    assert other_client.get(f"/api/cases/{fx.CASE_ID}", params={"customer_id": ME}).status_code == 403


def test_ac_06_unknown_cookie_is_unauthenticated_not_trusted(client):
    client.cookies.set("not_session", "S-forged0000000000")
    assert client.get("/api/me/cases").status_code == 401


# ---- AC-07: mode and dates -----------------------------------------------------------------------------------------
def test_ac_07_mode_is_stored_and_dates_follow_it(client, monkeypatch):
    monkeypatch.setattr(main, "today", lambda m, c=None: fx.REPLAY_TODAY if m == "replay" else dt.date(2026, 10, 4))
    sid = login(client, mode="replay")
    replay = client.get(f"/api/cases/{fx.CASE_ID}").json()
    assert replay["mode"] == "replay" and replay["deadline_countdown_days"] == 2
    client.put("/api/me/preferences", json={"language": "es", "mode": "live"})        # extra field: not writable
    assert client.app.state.sessions[sid]["mode"] == "replay"
    other = new_client(client.app)
    login(other, mode="live")
    live = other.get(f"/api/cases/{fx.CASE_ID}").json()
    assert live["mode"] == "live" and live["deadline_countdown_days"] == (fx.case_view().credit_deadline
                                                                          - dt.date(2026, 10, 4)).days


def test_ac_07_today_replay_is_demo_today_and_live_uses_the_country_time_zone(monkeypatch):
    monkeypatch.delenv("DEMO_TODAY", raising=False)
    assert main.today("replay", "MX") == dt.date(2026, 6, 1)
    monkeypatch.setenv("DEMO_TODAY", "2026-07-01")
    assert main.today("replay", "BR") == dt.date(2026, 7, 1)
    for country, zone in main.TIME_ZONES.items():
        assert main.today("live", country) == dt.datetime.now(ZoneInfo(zone)).date()
    c = new_client()
    r = c.post("/api/sessions", json={"customer_id": ME, "mode": "replay"}).json()
    assert r["today"] == "2026-07-01"                                                  # the session's `today` follows mode


# ---- EVAL_MODE ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("value", [None, "false", "", "no"])
def test_ac_02_eval_hooks_are_off_by_default(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("EVAL_MODE", raising=False)
    else:
        monkeypatch.setenv("EVAL_MODE", value)
    app = create_app()
    assert not [r for r in app.routes if "/api/eval" in getattr(r, "path", "")]
    assert new_client(app).post("/api/eval/seed", json=SEED).status_code == 404


def test_ac_02_eval_hooks_when_on(monkeypatch):
    monkeypatch.setenv("EVAL_MODE", "true")
    with new_client(create_app()) as c:
        r = c.post("/api/eval/seed", json=SEED).json()
        assert r["mode"] == "replay" and r["session_id"]
        c.cookies.set("not_session", r["session_id"])                      # D-019: the seeded session is the cookie
        st = c.get(f"/api/agent/threads/{r['thread_id']}/state")
        assert st.status_code == 200 and st.json()["mode"] == "replay"     # AC-08 (seed half): the stored mode
        assert c.app.state.sessions[r["session_id"]]["mode"] == "replay"
        none = c.post("/api/eval/seed", json={**SEED, "initial_state": {"customer_id": ME, "session": "none"}}).json()
        assert c.app.state.sessions[none["session_id"]]["customer_id"] is None      # §6.8: no customer kept
        c.cookies.set("not_session", none["session_id"])
        assert c.get(f"/api/agent/threads/{none['thread_id']}/state").json()["code"] == "UNAUTHENTICATED"
        assert c.get("/api/me/cases").json()["code"] == "UNAUTHENTICATED"
        exp = c.post("/api/eval/seed", json={**SEED, "initial_state": {"customer_id": ME, "session": "expired"}}).json()
        c.cookies.set("not_session", exp["session_id"])
        assert c.get("/api/me/cases").json()["code"] == "SESSION_EXPIRED"
        assert c.post("/api/eval/seed", json={**SEED, "initial_state": {"session": "x"}}).status_code == 400
        assert c.get("/api/eval/final-state/S-unknown").status_code == 404
        plain = c.post("/api/sessions", json={"customer_id": ME}).json()["session_id"]
        assert c.get(f"/api/eval/final-state/{plain}").status_code == 404           # a non-eval session has none
        c.post(f"/api/sessions/{plain}/verify", json={"otp": fx.OTP})
        c.app.state.sessions[plain]["expires_at"] = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
        assert c.post(f"/api/sessions/{plain}/verify", json={"otp": fx.OTP}).status_code == 410


def test_ac_02_console_handoff_follows_its_schema_and_filters(client):
    d = client.get(f"/api/console/cases/{fx.CASE_ID}", headers=BEARER).json()
    jsonschema.validate(d["handoff"], load_schema("handoff.schema.json"))
    assert client.get("/api/console/cases?zone=medium", headers=BEARER).json() == []
    assert client.get("/api/console/cases/K-000000", headers=BEARER).status_code == 404
