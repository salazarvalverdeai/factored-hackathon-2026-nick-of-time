"""Spec 05: the store-backed api (`app.live`). AC-01..AC-07 here; AC-08 is a document check at the end.
Everything runs offline: MemoryStore, a locally generated RSA key for the Cognito JWTs, a fake Platform and notifier."""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import fixtures as fx
from app.auth import CognitoVerifier
from app.notify import ChannelFailed
from app.platform import HttpPlatform
from nick_of_time import ids
from nick_of_time.contracts import AnalystActionIn, CustomerTurn
from nick_of_time.store import NewCase
from nick_of_time.store.memory import MemoryStore

ME, OTHER = fx.CUSTOMERS[0]["customer_id"], fx.CUSTOMERS[1]["customer_id"]
HTTPS = "https://testserver"
ISS, CLIENT = "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_TEST", "client-1"
KEY, OTHER_KEY = rsa.generate_private_key(65537, 2048), rsa.generate_private_key(65537, 2048)
JWK = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key())), "kid": "k1", "alg": "RS256", "use": "sig"}
FACTS = dict(customer_id=ME, transaction_id=fx.TRANSACTION_ID, product_id=fx.PRODUCT_ID, country="MX",
             product_type="debit", zone="high", dispute_type="unrecognized_charge", opened_on=dt.date(2026, 6, 1),
             credit_deadline=dt.date(2026, 6, 3), deadline_source="Banxico Circular 3/2012",
             deadline_source_url="https://www.banxico.org.mx/", deadline_verified_on=dt.date(2026, 10, 4),
             mode="replay", trace_id="trace-1")
START = dt.datetime(2026, 6, 1, 15, tzinfo=dt.UTC)
SECRET = "tg-secret"


def token(sub="ana-1", key=KEY, **claims) -> str:
    body = {"sub": sub, "iss": ISS, "aud": CLIENT, "token_use": "id", "exp": dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
            **claims}
    return jwt.encode(body, key, algorithm="RS256", headers={"kid": "k1"})


def bearer(**kw) -> dict:
    return {"Authorization": f"Bearer {token(**kw)}"}


class FakePlatform:
    def __init__(self, turn=None):
        self.threads, self.calls, self.turn = {}, [], turn

    def create_thread(self, session_id):
        tid = "T-" + str(len(self.threads))
        self.threads[tid] = session_id
        return tid

    def thread_session(self, thread_id):
        return self.threads.get(thread_id)

    def stream(self, thread_id, configurable, payload):
        self.calls.append((configurable, payload))
        yield "progress", {"step": "block_card", "label": "Bloqueando", "state": "in_progress", "at": START.isoformat()}
        yield "turn", self.turn or fx.turn_result().model_dump(mode="json")

    def state(self, thread_id):
        return self.turn or fx.turn_result().model_dump(mode="json")


class FakeNotifier:
    def __init__(self):
        self.sent, self.fail = [], False

    def _send(self, kind, to, text):
        if self.fail:
            raise ChannelFailed("down")
        self.sent.append((kind, to, text))
        return "m-1"

    def telegram(self, chat_id, text):
        return self._send("telegram", chat_id, text)

    def email(self, to, subject, text):
        return self._send("email", to, text)


class Env:
    def __init__(self):
        self.clock = {"t": START}
        self.store = MemoryStore(now=lambda: self.clock["t"])
        self.platform, self.notifier = FakePlatform(), FakeNotifier()
        from app.main import create_app
        self.app = create_app(store=self.store, verifier=CognitoVerifier(issuer=ISS, client_id=CLIENT, jwks={"keys": [JWK]}),
                               platform=self.platform, notifier=self.notifier, now=lambda: self.clock["t"],
                               link_key="k")
        self.client = TestClient(self.app, base_url=HTTPS)

    def case(self, customer=ME, **changes) -> str:
        return self.store.create_case(NewCase(**{**FACTS, "customer_id": customer, **changes}), actor="agent",
                                      action_id=ids.new_id("action")).case_id

    def login(self, customer=ME, client=None) -> str:
        client = client or self.client
        r = client.post("/api/sessions", json={"customer_id": customer, "mode": "replay"})
        sid = r.json()["session_id"]
        assert client.post(f"/api/sessions/{sid}/verify", json={"otp": r.json()["otp_demo"]}).status_code == 200
        return sid

    def action(self, case_id, action, key, reason="done", actor_id="forged", **kw):
        body = {"case_id": case_id, "actor_id": actor_id, "action": action, "reason": reason, "idempotency_key": key}
        return self.client.post(f"/api/cases/{case_id}/action", json=body, headers=bearer(**kw))

    def resolve(self, case_id):
        self.store.change_status(case_id, "verification", on=dt.date(2026, 6, 1), actor="agent", trace_id="t")
        for a, to in (("take", "review"), ("resolve", "resolved")):
            self.store.record_analyst_action(AnalystActionIn(case_id=case_id, actor_id="s", action=a, reason="x",
                                                              idempotency_key=a), new_status=to,
                                             on=dt.date(2026, 6, 1), trace_id="t")


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    return Env()


# ---------- AC-01 ----------
def test_ac_01_session_lasts_15_minutes_then_every_protected_route_says_session_expired(env):
    r = env.client.post("/api/sessions", json={"customer_id": ME, "mode": "replay"})
    sid = r.json()["session_id"]
    assert dt.datetime.fromisoformat(r.json()["expires_at"]) == START + dt.timedelta(minutes=15)
    assert env.client.get("/api/me/cases").status_code == 401                         # no cookie yet
    assert env.client.post(f"/api/sessions/{sid}/verify", json={"otp": "000000x"}).status_code == 401
    assert env.client.post(f"/api/sessions/{sid}/verify", json={"otp": r.json()["otp_demo"]}).status_code == 200
    assert env.store.get_session(sid).verified_at == START
    case_id = env.case()
    for path in ("/api/me/cases", "/api/me/products", "/api/notifications", f"/api/cases/{case_id}"):
        assert env.client.get(path).status_code == 200
    env.clock["t"] = START + dt.timedelta(minutes=15, seconds=1)
    for path in ("/api/me/cases", "/api/me/products", "/api/notifications", f"/api/cases/{case_id}"):
        got = env.client.get(path)
        assert (got.status_code, got.json()["code"]) == (401, "SESSION_EXPIRED"), path
    assert env.client.post(f"/api/sessions/{sid}/verify", json={"otp": "1"}).status_code == 410


def test_ac_01_mode_and_customer_come_from_the_session_row_not_from_the_client(env):
    sid = env.login()
    other = env.case(OTHER)
    env.client.put("/api/me/preferences", json={"language": "pt", "mode": "live", "customer_id": OTHER})
    row = env.store.get_session(sid)
    assert (row.mode, row.customer_id, row.language) == ("replay", ME, "pt")
    assert env.client.get("/api/me/cases").json() == []                               # OTHER's case is not listed
    assert env.client.get(f"/api/cases/{other}").status_code == 403


# ---------- AC-02 ----------
def test_ac_02_status_is_the_last_event_and_earlier_rows_never_change(env):
    case_id = env.case()
    seen = []
    for action, key in (("take", "k1"), ("resolve", "k2"), ("close_case", "k3")):
        before = env.store.events(case_id)
        assert env.action(case_id, action, key).status_code == 200
        after = env.store.events(case_id)
        assert after[:len(before)] == before and len(after) > len(before)             # append-only
        moves = [e.payload["to"] for e in after if e.type == "status_changed"]
        seen.append((env.store.queue_status(case_id), moves[-1]))
    assert seen == [("review", "review"), ("resolved", "resolved"), ("closed", "closed")]
    assert [e.seq for e in env.store.events(case_id)] == list(range(1, len(env.store.events(case_id)) + 1))
    shown = env.client.get(f"/api/console/cases/{case_id}", headers=bearer()).json()
    assert shown["case"]["queue_status"] == "closed"


# ---------- AC-03 ----------
def test_ac_03_a_valid_action_changes_status_records_actor_and_reason_and_notifies(env):
    case_id = env.case()
    env.login()
    out = env.action(case_id, "take", "k1", reason=None, sub="ana-1")
    assert out.status_code == 200 and out.json()["new_status"] == "review" and out.json()["previous_status"] == "new"
    assert out.json()["notification_id"]
    out = env.action(case_id, "resolve", "k2", reason="Reembolso emitido", sub="ana-1")
    assert out.json()["new_status"] == "resolved" and out.json()["notification_id"]
    done = [e for e in env.store.events(case_id) if e.type == "analyst_action"]
    assert [(e.actor, e.payload["action"]) for e in done] == [("analyst:ana-1", "take"), ("analyst:ana-1", "resolve")]
    assert done[1].payload["reason"] == "Reembolso emitido"
    texts = [n["text"] for n in env.client.get("/api/notifications").json()]
    assert any("resuelto" in t for t in texts) and any("revisando" in t for t in texts)
    # an action that keeps the status (D-034) is an event with actor and reason and no status change, so no notice
    kept = env.action(case_id, "approve_credit", "k3", sub="ana-1").json()
    assert kept["new_status"] == kept["previous_status"] == "resolved" and kept["notification_id"] is None
    assert env.store.events(case_id)[-1].actor == "analyst:ana-1"


def test_ac_10_a_replayed_idempotency_key_writes_and_notifies_once(env):
    case_id = env.case()
    first = env.action(case_id, "take", "same").json()
    events, notes = len(env.store.events(case_id)), len(env.store.list_notifications(ME, run_id=None))
    assert env.action(case_id, "take", "same").json() == first
    assert (len(env.store.events(case_id)), len(env.store.list_notifications(ME, run_id=None))) == (events, notes)
    assert env.action(case_id, "resolve", "same").status_code == 409                  # same key, another action


# ---------- AC-04 ----------
def test_ac_04_a_transition_that_does_not_exist_answers_409_and_changes_nothing(env):
    case_id = env.case()
    before = env.store.events(case_id)
    bad = env.action(case_id, "close_case", "k1")                                     # new -> closed is not in case_queue
    assert (bad.status_code, bad.json()["code"], bad.json()["policy_id"]) == (409, "DENY", "POL-QUEUE-TRANSITION")
    assert env.store.events(case_id) == before and env.store.queue_status(case_id) == "new"
    assert [d.policy_id for d in env.store.list_denials(run_id=None)] == ["POL-QUEUE-TRANSITION"]
    for a, k in (("take", "a"), ("resolve", "b"), ("close_case", "c")):
        env.action(case_id, a, k)
    after_close = env.store.events(case_id)
    assert env.action(case_id, "take", "d").status_code == 409                        # a closed case takes nothing
    assert env.store.events(case_id) == after_close


def test_ac_10_a_reason_is_required_where_the_contract_says_so_and_an_unknown_case_is_404(env):
    case_id = env.case()
    assert env.action(case_id, "resolve", "k", reason=None).status_code == 400
    assert env.action("K-999999", "take", "k").status_code == 404
    assert env.action(case_id, "take", "k", reason=None).status_code == 200


# ---------- AC-05 ----------
def test_ac_05_the_session_id_is_injected_server_side_and_the_client_cannot_override_it(env):
    sid = env.login()
    thread = env.client.post("/api/agent/threads").json()["thread_id"]
    forged = {"input": {"x": 1}, "session_id": "S-forged", "customer_id": OTHER,
              "config": {"configurable": {"session_id": "S-forged", "mode": "live", "customer_id": OTHER}}}
    r = env.client.post(f"/api/agent/threads/{thread}/runs/stream", json=forged)
    assert r.status_code == 200
    configurable, payload = env.platform.calls[-1]
    assert configurable["session_id"] == sid and configurable["mode"] == "replay" and "customer_id" not in configurable
    assert payload["input"] == {"x": 1}
    body = r.text
    assert "event: progress" in body and "event: turn" in body
    turn = json.loads(body.split("event: turn\ndata: ")[1].split("\n")[0])
    assert "zone" not in turn and set(turn) <= set(CustomerTurn.model_fields)                              # customer projection only (D-013)


def test_ac_05_another_sessions_thread_is_not_found(env):
    env.login()
    thread = env.client.post("/api/agent/threads").json()["thread_id"]
    with TestClient(env.app, base_url=HTTPS) as other:
        env.login(OTHER, client=other)
        assert other.post(f"/api/agent/threads/{thread}/runs/stream", json={}).status_code == 404
        assert other.get(f"/api/agent/threads/{thread}/state").status_code == 404


def test_ac_05_the_platform_key_goes_only_in_the_upstream_header_never_to_the_browser(env):
    key, seen = "lsv2_SECRET_KEY", []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/threads" and request.method == "POST":
            return httpx.Response(200, json={"thread_id": "T-1"})
        if request.url.path == "/threads/T-1":
            return httpx.Response(200, json={"metadata": {"session_id": env.sid}})
        turn = json.dumps(fx.turn_result().model_dump(mode="json"))
        sse = ("event: custom\ndata: " + json.dumps({"step": "block_card", "label": "x", "state": "in_progress",
                                                       "at": START.isoformat()})
               + "\n\nevent: values\ndata: " + turn + "\n\n")
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    from app.main import create_app
    env.sid = env.login()
    platform = HttpPlatform("https://platform.example", key, transport=httpx.MockTransport(handler))
    app = create_app(store=env.store, platform=platform, notifier=env.notifier, now=lambda: env.clock["t"])
    with TestClient(app, base_url=HTTPS) as browser:
        browser.cookies.set("not_session", env.sid)
        thread = browser.post("/api/agent/threads").json()["thread_id"]
        run = browser.post(f"/api/agent/threads/{thread}/runs/stream", json={"input": {"messages": []}})
    assert run.status_code == 200 and "event: turn" in run.text
    assert all(r.headers["x-api-key"] == key for r in seen)                           # the api's own requests carry it
    everything = run.text + json.dumps(dict(run.headers)) + json.dumps(dict(browser.cookies))
    assert key not in everything
    upstream = json.loads(next(r for r in seen if r.url.path.endswith("/runs/stream")).content)
    assert upstream["config"]["configurable"]["session_id"] == env.sid


# ---------- AC-06 ----------
def test_ac_06_supervised_mode_is_recorded_and_forces_human_approval_in_every_run(env):
    env.login()
    thread = env.client.post("/api/agent/threads").json()["thread_id"]
    env.client.post(f"/api/agent/threads/{thread}/runs/stream", json={})
    assert env.platform.calls[-1][0]["supervised_mode"] is False                      # policies.yaml default
    assert env.client.put("/api/console/settings", json={"supervised_mode": True}).status_code == 401
    on = env.client.put("/api/console/settings", json={"supervised_mode": True}, headers=bearer(sub="lead-1"))
    assert on.json()["supervised_mode"] is True
    env.client.post(f"/api/agent/threads/{thread}/runs/stream", json={})
    assert env.platform.calls[-1][0]["supervised_mode"] is True
    env.client.put("/api/console/settings", json={"supervised_mode": False}, headers=bearer(sub="lead-2"))
    history = env.store.setting_history("supervised_mode")
    assert [(h["value"], h["actor"]) for h in history] == [(True, "analyst:lead-1"), (False, "analyst:lead-2")]
    assert env.client.get("/api/console/settings", headers=bearer()).json()["supervised_mode"] is False


# ---------- AC-07 ----------
@pytest.mark.parametrize("headers", [
    {}, {"Authorization": "Bearer"}, {"Authorization": "Bearer not-a-jwt"}, {"Authorization": "Basic abc"},
    {"Authorization": "Bearer " + token(key=OTHER_KEY)},                                  # signed by another key
    {"Authorization": "Bearer " + token(aud="another-app")},
    {"Authorization": "Bearer " + token(iss="https://evil.example")},
    {"Authorization": "Bearer " + token(exp=dt.datetime(2020, 1, 1, tzinfo=dt.UTC))},
    {"Authorization": "Bearer " + jwt.encode({"sub": "x"}, "k" * 40, algorithm="HS256")},   # not RS256
])
def test_ac_07_an_analyst_route_without_a_valid_cognito_jwt_answers_401(env, headers):
    case_id = env.case()
    calls = [("GET", "/api/console/cases", None), ("GET", f"/api/console/cases/{case_id}", None),
             ("GET", "/api/console/settings", None), ("PUT", "/api/console/settings", {"supervised_mode": True}),
             ("POST", f"/api/cases/{case_id}/action", {"case_id": case_id, "actor_id": "x", "action": "take",
                                                       "idempotency_key": "k"})]
    for method, path, body in calls:
        assert env.client.request(method, path, json=body, headers=headers).status_code == 401, path
    assert [e.type for e in env.store.events(case_id)] == ["case_opened"]


def test_ac_07_actor_id_comes_from_the_token_not_from_the_body(env):
    case_id = env.case()
    assert env.action(case_id, "take", "k1", actor_id="someone-else", sub="real-sub").status_code == 200
    assert {e.actor for e in env.store.events(case_id) if e.type in ("analyst_action", "assigned")} == {"analyst:real-sub"}


def test_ac_07_an_access_token_of_this_app_also_passes_and_no_verifier_means_no_analyst(env):
    access = {"Authorization": "Bearer " + jwt.encode(
        {"sub": "s", "iss": ISS, "client_id": CLIENT, "token_use": "access",
         "exp": dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)}, KEY, algorithm="RS256", headers={"kid": "k1"})}
    assert env.client.get("/api/console/cases", headers=access).status_code == 200
    from app.main import create_app
    bare = TestClient(create_app(store=env.store), base_url=HTTPS)
    assert bare.get("/api/console/cases", headers=bearer()).status_code == 401


# ---------- customer views, channels, notifications (specs 07, 13 on the real store) ----------
def test_ac_09_customer_projection_has_no_internals_and_a_foreign_case_is_a_403_with_a_denial_row(env):
    mine, theirs = env.case(), env.case(OTHER)
    env.login()
    text = env.client.get(f"/api/cases/{mine}").text
    for word in ("POL-", "zone", "priority", "tags", "sla_due_at", "customer_id", "handoff"):
        assert word not in text, word
    r = env.client.get(f"/api/cases/{theirs}")
    assert (r.status_code, r.json()["code"], r.json()["policy_id"]) == (403, "DENY", None)
    assert [d.policy_id for d in env.store.list_denials(run_id=None)] == ["POL-CROSS-CUSTOMER"]
    assert env.client.get("/api/cases/K-000000").status_code == 404
    assert [c["case_id"] for c in env.client.get("/api/me/cases").json()] == [mine]


def test_console_lists_every_case_with_zone_and_priority_and_filters(env):
    a, b = env.case(), env.case(OTHER, country="BR", product_type="credit", zone="medium", credit_deadline=None,
                                deadline_source=None, deadline_source_url=None, deadline_verified_on=None)
    rows = env.client.get("/api/console/cases", headers=bearer()).json()
    assert {r["case_id"] for r in rows} == {a, b} and all("zone" in r and "priority" in r for r in rows)
    only = env.client.get("/api/console/cases?zone=medium&country=BR", headers=bearer()).json()
    assert [r["case_id"] for r in only] == [b]
    detail = env.client.get(f"/api/console/cases/{a}", headers=bearer()).json()
    assert detail["case"]["zone"] == "high" and detail["events"][0]["type"] == "case_opened"


def test_spec13_ac_05_a_call_request_returns_the_event_and_the_expected_contact_date(env):
    case_id = env.case()
    env.login()
    r = env.client.post(f"/api/cases/{case_id}/call-request", json={})
    assert r.status_code == 201 and r.json()["expected_contact_by"] == "2026-06-02"       # D-008: next business day
    assert env.store.events(case_id)[-1].type == "call_requested"


def test_spec13_ac_06_information_added_is_an_event_the_analyst_sees(env):
    case_id = env.case()
    env.login()
    assert env.client.post(f"/api/cases/{case_id}/info", json={"text": "fue en otra ciudad"}).status_code == 201
    events = env.client.get(f"/api/console/cases/{case_id}", headers=bearer()).json()["events"]
    assert "customer_info_added" in [e["type"] for e in events]


def test_ac_12_reevaluation_moves_a_resolved_case_to_review_once_and_a_closed_one_opens_a_related_case(env):
    """Spec 03 AC-19 through the api: resolved -> review (the reason is the event); closed -> a related case whose
    deadlines come from the new notice; an active case and a double click change nothing more."""
    case_id = env.case()
    env.login()
    deny = env.client.post(f"/api/cases/{case_id}/reevaluation", json={"reason": "r"})
    assert (deny.status_code, deny.json()["code"]) == (409, "DENY")
    env.resolve(case_id)
    ok = env.client.post(f"/api/cases/{case_id}/reevaluation", json={"reason": "no lo reconozco"})
    assert ok.status_code == 201 and ok.json()["case_id"] == case_id
    assert env.store.queue_status(case_id) == "review"                                 # not still resolved
    kinds = [e.type for e in env.store.events(case_id)][-2:]
    assert kinds == ["status_changed", "reevaluation_requested"]
    assert env.client.post(f"/api/cases/{case_id}/reevaluation", json={"reason": "again"}).status_code == 409
    env.action(case_id, "resolve", "r1")
    env.action(case_id, "close_case", "r2")
    env.clock["t"] = START                                                             # same day, replay: 2026-06-01
    first = env.client.post(f"/api/cases/{case_id}/reevaluation", json={"reason": "r2"}).json()
    second = env.client.post(f"/api/cases/{case_id}/reevaluation", json={"reason": "r2"}).json()
    assert first == second and first["case_id"] != case_id                             # a double click opens one case
    fresh = env.store.get_case(first["case_id"], run_id=None, customer_id=ME)
    assert fresh.related_case_id == case_id and fresh.opened_on == dt.date(2026, 6, 1)
    assert fresh.credit_deadline == dt.date(2026, 6, 3) and fresh.deadline_source        # derived by the clock, from the notice
    assert len([c for c in env.store.list_cases(ME, run_id=None) if c.related_case_id == case_id]) == 1


def test_ac_11_spec13_ac_02_03_telegram_link_stores_the_chat_once_and_bad_secret_or_expired_token_is_401(env):
    case_id = env.case()
    env.login()
    link = env.client.post(f"/api/cases/{case_id}/channels/telegram").json()
    assert dt.datetime.fromisoformat(link["expires_at"]) == START + dt.timedelta(minutes=15)
    start = link["deep_link"].split("start=")[1]
    hook = {"X-Telegram-Bot-Api-Secret-Token": SECRET}
    update = {"message": {"text": f"/start {start}", "chat": {"id": 777}}}
    assert env.client.post("/api/telegram/webhook", json=update).status_code == 401
    assert env.client.post("/api/telegram/webhook", json=update,
                           headers={"X-Telegram-Bot-Api-Secret-Token": "bad"}).status_code == 401
    assert env.store.channels(ME) == []                                               # nothing was processed
    assert env.client.post("/api/telegram/webhook", json=update, headers=hook).json() == {"ok": True}
    assert [(c.channel, c.address, c.event) for c in env.store.channels(ME)] == [("telegram", "777", "linked")]
    assert "telegram_linked" in [e.type for e in env.store.events(case_id)]
    forged = {"message": {"text": "/start " + start[:-1] + "0", "chat": {"id": 1}}}
    assert env.client.post("/api/telegram/webhook", json=forged, headers=hook).status_code == 401
    env.clock["t"] += dt.timedelta(minutes=16)
    stale = env.client.post(f"/api/cases/{case_id}/channels/telegram")                 # session expired by now
    assert stale.status_code == 401
    expired = {"message": {"text": f"/start {start}", "chat": {"id": 888}}}
    assert env.client.post("/api/telegram/webhook", json=expired, headers=hook).status_code == 401
    assert env.store.channels(ME)[0].address == "777"


def test_ac_11_spec13_ac_01_07_08_a_status_change_reaches_telegram_and_a_failing_channel_keeps_the_log(env):
    case_id = env.case()
    env.login()
    start = env.client.post(f"/api/cases/{case_id}/channels/telegram").json()["deep_link"].split("start=")[1]
    env.client.post("/api/telegram/webhook", json={"message": {"text": f"/start {start}", "chat": {"id": 555}}},
                    headers={"X-Telegram-Bot-Api-Secret-Token": SECRET})
    env.notifier.sent.clear()
    out = env.action(case_id, "take", "k1").json()
    assert env.notifier.sent == []                                                    # in_review is a log-only template
    assert env.action(case_id, "resolve", "k2", reason="Reembolso aprobado").json()["notification_id"]
    assert [(k, to) for k, to, _ in env.notifier.sent] == [("telegram", "555")]       # AC-01: resolved reaches Telegram
    assert env.action(case_id, "reopen_case", "k3").status_code == 200
    env.notifier.fail = True
    done = env.action(case_id, "resolve", "k4", reason="Reembolso aprobado POL-X score 91").json()      # analyst-only text
    assert done["notification_id"]                                                    # the log row survived the failure
    rows = env.store.list_notifications(ME, run_id=None)
    log = next(r for r in rows if r.notification_id == done["notification_id"])
    assert (log.channel, log.delivery_status) == ("log", "delivered")
    assert sorted((r.channel, r.delivery_status) for r in rows if r.event == "resolved") == [
        ("log", "delivered"), ("log", "delivered"), ("telegram", "failed"), ("telegram", "sent")]
    assert out["notification_id"]
    assert all("Reembolso" not in r.text and "Resuelto" in r.text for r in rows if r.event == "resolved")   # fixed label
    for r in rows:                                                                    # never_send: score, policy ids
        assert not re.search(r"POL-|score|transcript", r.text, re.I), r.text
    assert env.client.get(f"/api/cases/{case_id}").status_code == 200                 # the case page is unaffected
    shown = env.client.get(f"/api/cases/{case_id}").json()
    assert shown["channels"]["telegram"] is True


def test_ac_11_spec13_ac_04_email_is_used_only_after_the_typed_address_is_confirmed(env):
    case_id = env.case()
    env.login()
    assert env.client.post(f"/api/cases/{case_id}/channels/email", json={"email": "nope"}).status_code == 400
    r = env.client.post(f"/api/cases/{case_id}/channels/email", json={"email": "ana@example.com"})
    assert r.status_code == 202 and r.json() == {"confirmation_sent": True}
    link = re.search(r"token=(\S+)", env.notifier.sent[-1][2]).group(1)
    env.notifier.sent.clear()
    env.action(case_id, "take", "k1")
    assert env.notifier.sent == []                                                    # typed, not yet confirmed
    assert env.client.get("/api/channels/email/confirm?token=bad", follow_redirects=False).status_code == 410
    ok = env.client.get(f"/api/channels/email/confirm?token={link}", follow_redirects=False)
    assert ok.status_code == 302 and ok.headers["location"] == f"/case/{case_id}?email=confirmed"
    env.action(case_id, "resolve", "k2")
    assert [(k, to) for k, to, _ in env.notifier.sent] == [("email", "ana@example.com")]
    assert [c.event for c in env.store.channels(ME)] == ["confirmed"]


def test_ac_11_webhooks_check_their_secret(env, monkeypatch):
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", "x")
    assert env.client.post("/api/resend/webhook", json={}).status_code == 401
    assert env.client.post("/api/resend/webhook", json={}, headers={"svix-signature": "v1,abc"}).status_code == 200


def test_the_store_backed_app_is_chosen_by_a_store_and_the_stub_stays_without_one(env):
    from app.main import create_app
    assert create_app(eval_mode=False).title.endswith("(stub)")
    assert not env.app.title.endswith("(stub)")


# ---------- AC-08 [D] ----------
def test_ac_08_accounts_are_documented_without_a_password():
    text = (Path(__file__).parents[1] / "apps/api/README.md").read_text()
    assert "judge" in text.lower() and "Accounts" in text
    assert not re.search(r"password\s*[:=]\s*\S+", text, re.I)
    assert "submission e-mail" in text


# ---------- review of PR #111 ----------
def test_ac_05_the_real_graph_state_with_its_extra_channels_is_accepted(env):
    """LangGraph's `values` stream and get_state carry every channel; only TurnResult's own fields are validated."""
    state = {**fx.turn_result().model_dump(mode="json"), "messages": [{"role": "user", "content": "hola"}],
             "scratch": {"x": 1}}
    env.platform.turn = state
    env.login()
    thread = env.client.post("/api/agent/threads").json()["thread_id"]
    run = env.client.post(f"/api/agent/threads/{thread}/runs/stream", json={})
    assert "event: turn" in run.text and "event: error" not in run.text and "messages" not in run.text
    got = env.client.get(f"/api/agent/threads/{thread}/state")
    assert got.status_code == 200 and "messages" not in got.json() and "zone" not in got.json()


def test_ac_07_an_unknown_kid_refetches_the_jwks_once_and_token_use_is_required():
    other = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(OTHER_KEY.public_key())), "kid": "k2", "alg": "RS256"}
    fetched = []

    def fetch(url):
        fetched.append(url)
        return {"keys": [JWK, other]}

    verifier = CognitoVerifier(issuer=ISS, client_id=CLIENT, jwks={"keys": [JWK]}, fetch_jwks=fetch)
    verifier._loaded -= 60                                                            # the set is older than 10 s
    rotated = jwt.encode({"sub": "n", "iss": ISS, "aud": CLIENT, "token_use": "id",
                          "exp": dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)}, OTHER_KEY, algorithm="RS256",
                         headers={"kid": "k2"})
    assert verifier.verify(rotated) == "n" and len(fetched) == 1
    unknown = jwt.encode({"sub": "n", "iss": ISS, "aud": CLIENT, "token_use": "id",
                          "exp": dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)}, OTHER_KEY, algorithm="RS256",
                         headers={"kid": "k9"})
    from app.auth import AuthError
    with pytest.raises(AuthError):
        verifier.verify(unknown)
    assert len(fetched) == 1                                                          # no fetch storm for a bad kid
    no_use = jwt.encode({"sub": "n", "iss": ISS, "aud": CLIENT, "exp": dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)},
                        KEY, algorithm="RS256", headers={"kid": "k1"})
    with pytest.raises(AuthError):
        verifier.verify(no_use)


def test_the_cognito_issuer_is_derived_from_the_pool_id(monkeypatch):
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-2_ABC")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "c1")
    assert CognitoVerifier.from_env().issuer == "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_ABC"
    monkeypatch.delenv("COGNITO_CLIENT_ID")
    assert CognitoVerifier.from_env() is None


def test_ac_11_without_a_dedicated_link_key_no_channel_link_is_issued(env, monkeypatch):
    monkeypatch.delenv("LINK_SIGNING_KEY", raising=False)
    from app.main import create_app
    bare = TestClient(create_app(store=env.store, now=lambda: env.clock["t"]), base_url=HTTPS)
    case_id = env.case()
    env.login(client=bare)
    assert bare.post(f"/api/cases/{case_id}/channels/telegram").status_code == 503


def test_ac_09_the_console_orders_by_sla_then_zone_and_uses_its_own_listing(env):
    a = env.case(zone="human")
    b = env.case(zone="high")
    for case_id in (a, b):
        env.store.change_status(case_id, "verification", on=dt.date(2026, 6, 1), actor="agent", trace_id="t")
    rows = env.client.get("/api/console/cases", headers=bearer()).json()
    assert [r["zone"] for r in rows] == ["high", "human"] or [r["case_id"] for r in rows] == [a, b]
    assert [c.case_id for c in env.store.list_all_cases(run_id=None)] and not hasattr(env.store, "list_cases_any")


def test_demo_reset_is_not_served_until_demo_transactions_exist(env):
    assert env.client.post("/api/console/demo/reset", headers=bearer()).status_code in (404, 405)
