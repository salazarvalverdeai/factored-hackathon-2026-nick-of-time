"""Spec 08 AC-22: `GET /api/console/cases/{id}/conversation`, the case's chat history for the analyst.

The api marks a thread with the case its turn names (Platform thread metadata), only for the session's own case in
its run; the console reads the marked threads' checkpoints back and returns only the customer-visible messages (the
customer's texts and the agent's replies). Offline: MemoryStore and a fake Platform that keeps checkpoints.
"""
from __future__ import annotations

import datetime as dt
import json

import httpx
import pytest

from app import fixtures as fx
from app.console import transcript
from app.platform import HttpPlatform
from tests.test_spec05_api import ME, OTHER, FakePlatform, bearer
from tests.test_spec08_assisted_console import DEMO_RUN, Env, production_runs  # noqa: F401 - autouse fixture

SAID = "No reconozco el cargo de TIENDA X de ayer, por favor bloqueen mi tarjeta"


class ChatPlatform(FakePlatform):
    """Keeps each run as LangGraph checkpoints: the input, a mid-run state with internals, and the end of the turn."""

    def __init__(self, clock):
        super().__init__()
        self.clock, self.tags, self.checkpoints = clock, {}, {}

    def stream(self, thread_id, configurable, payload):
        self.calls.append((configurable, payload))
        said = payload["input"]["messages"]
        cps = self.checkpoints.setdefault(thread_id, [])
        last = cps[-1]["values"] if cps else {}

        def at(seconds):
            return (self.clock["t"] + dt.timedelta(seconds=seconds)).isoformat()
        cps.append({"values": {**last, "messages": said}, "next": ["__start__"], "created_at": at(0)})
        cps.append({"values": {**last, "messages": said, "trace_id": self.turn["trace_id"], "zone": "high",
                               "score": {"score": 87.0, "source": "dataset"}, "route": {"rule_ids": ["POL-ZONE-HIGH"]}},
                    "next": ["respond"], "created_at": at(1)})
        cps.append({"values": {**self.turn, "messages": [], "score": {"score": 87.0}}, "next": [], "created_at": at(2)})
        yield "turn", self.turn

    def tag_case(self, thread_id, case_id):
        self.tags.setdefault(case_id, set()).add(thread_id)

    def case_threads(self, case_id):
        return [(t, self.threads.get(t)) for t in sorted(self.tags.get(case_id, ()))]

    def history(self, thread_id):
        return list(reversed(self.checkpoints.get(thread_id, [])))          # newest first, as Platform answers


def turn(case_id, trace, reply="Bloqueamos tu tarjeta y abrimos el caso."):
    return {**fx.turn_result().model_dump(mode="json"), "case_id": case_id, "trace_id": trace, "reply": reply,
            "handoff": None, "receipt": None}


@pytest.fixture
def env():
    return Env(platform=ChatPlatform)


def chat(env, customer=ME, texts=(SAID,), case_id=None, trace="tr-c1"):
    """A session of `customer` that sends `texts`, one turn each, every turn naming `case_id`."""
    r = env.client.post("/api/sessions", json={"customer_id": customer, "mode": "replay"})
    sid = r.json()["session_id"]
    assert env.client.post(f"/api/sessions/{sid}/verify", json={"otp": r.json()["otp_demo"]}).status_code == 200
    thread = env.client.post("/api/agent/threads").json()["thread_id"]
    for n, text in enumerate(texts):
        env.platform.turn = turn(case_id, f"{trace}-{n}")
        body = {"input": {"messages": [{"role": "user", "content": text}]}}
        assert env.client.post(f"/api/agent/threads/{thread}/runs/stream", json=body).status_code == 200
        env.clock["t"] += dt.timedelta(minutes=1)
    return sid, thread


def conversation(env, case_id, **kw):
    return env.client.get(f"/api/console/cases/{case_id}/conversation", headers=bearer(**kw))


def test_ac_22_the_conversation_is_analyst_only():
    e = Env()
    c = e.case()
    assert e.client.get(f"/api/console/cases/{c.case_id}/conversation").status_code == 401
    assert e.client.get(f"/api/console/cases/{c.case_id}/conversation",
                        headers={"Authorization": "Bearer forged"}).status_code == 401


def test_ac_22_returns_only_the_customer_visible_messages_of_the_case_threads(env):
    c = env.case()
    sid, thread = chat(env, texts=(SAID, "¿Cuándo me devuelven el dinero?"), case_id=c.case_id)
    got = conversation(env, c.case_id)
    assert got.status_code == 200
    [t] = got.json()["threads"]
    assert t["thread_id"] == thread
    assert t["session_started_at"] == env.store.get_session(sid).created_at.isoformat()
    assert [(m["role"], m["text"]) for m in t["messages"]] == [
        ("customer", SAID), ("agent", "Bloqueamos tu tarjeta y abrimos el caso."),
        ("customer", "¿Cuándo me devuelven el dinero?"), ("agent", "Bloqueamos tu tarjeta y abrimos el caso.")]
    assert all(set(m) == {"role", "text", "at"} for m in t["messages"])
    raw = got.text
    for internal in ("87", "POL-", "zone", "score", "handoff", "trace_id", "tr-c1", "G-IN-01"):
        assert internal not in raw, internal                                  # never internal state


def test_ac_22_a_thread_of_another_customer_or_run_is_refused(env):
    mine = env.case()
    demo_case = env.case(run_id=DEMO_RUN, transaction_id="TRX-FIXTURE0000000000002")
    chat(env, case_id=demo_case.case_id, trace="tr-x")                      # a production session naming a demo case
    assert env.platform.tags.get(demo_case.case_id) is None                  # the api never marks it
    _, foreign = chat(env, customer=OTHER, case_id=mine.case_id, trace="tr-o")
    assert env.platform.tags.get(mine.case_id) is None                       # another customer's turn: not marked
    env.platform.tag_case(foreign, mine.case_id)                             # a mark the api did not write
    assert conversation(env, mine.case_id).json()["threads"] == []           # its session is another customer's
    other_run = env.store.create_session(customer_id=ME, otp_hash="x", run_id=DEMO_RUN, language="es", mode="replay",
                                         expires_at=env.clock["t"] + dt.timedelta(minutes=15))
    env.platform.threads["T-demo"] = other_run.session_id
    env.platform.tag_case("T-demo", mine.case_id)
    assert conversation(env, mine.case_id).json()["threads"] == []           # same customer, another run
    assert conversation(env, demo_case.case_id).json()["threads"] == []
    hidden = env.case(run_id="eval-run-1", transaction_id="TRX-FIXTURE0000000000003")
    assert conversation(env, hidden.case_id).status_code == 404               # eval runs never reach the console


def test_ac_22_the_transcript_never_reaches_a_notification(env):
    c = env.case()
    chat(env, case_id=c.case_id)
    assert conversation(env, c.case_id).status_code == 200
    body = {"case_id": c.case_id, "actor_id": "x", "action": "take", "reason": None, "idempotency_key": "k-take"}
    assert env.client.post(f"/api/cases/{c.case_id}/action", json=body, headers=bearer()).status_code == 200
    notes = env.store.list_notifications(ME, run_id=None)
    assert notes and all(SAID not in n.text for n in notes)
    events = [e.payload for e in env.store.events(c.case_id) if e.type == "notification_sent"]
    assert all(SAID not in str(p) for p in events)


def test_ac_22_a_platform_without_thread_search_is_unavailable_and_a_chip_turn_shows_only_the_reply():
    e = Env()                                                                # the spec 05 fake: no thread marks
    assert conversation(e, e.case().case_id).status_code == 503
    states = [{"values": {"messages": [], "trace_id": "a", "reply": "Hola"}, "next": [],
               "created_at": "2026-06-01T15:00:00+00:00"},
              {"values": {"messages": [], "trace_id": "a", "reply": "Hola", "score": 90}, "next": ["respond"],
               "created_at": "2026-06-01T15:01:00+00:00"},
              {"values": {"messages": [], "trace_id": "b", "reply": "Hola"}, "next": ["respond"],
               "created_at": "2026-06-01T15:01:30+00:00"},
              {"values": {"messages": [], "trace_id": "b", "reply": "Listo"}, "next": [],
               "created_at": "2026-06-01T15:02:00+00:00"}]
    assert [(m["role"], m["text"]) for m in transcript(states)] == [("agent", "Hola"), ("agent", "Listo")]


def test_ac_22_the_http_platform_marks_searches_and_reads_history():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, json.loads(request.content or b"{}")))
        if request.url.path == "/threads/search":
            return httpx.Response(200, json=[{"thread_id": "t1", "metadata": {"session_id": "S-1", "case:K-1": True}}])
        if request.url.path.endswith("/history"):
            return httpx.Response(200, json=[{"values": {}, "next": [], "created_at": "2026-06-01T15:00:00Z"}])
        return httpx.Response(200, json={})
    p = HttpPlatform("https://platform.test", "key", transport=httpx.MockTransport(handler))
    p.tag_case("t1", "K-1")
    assert p.case_threads("K-1") == [("t1", "S-1")]
    assert len(p.history("t1")) == 1
    assert seen[0] == ("PATCH", "/threads/t1", {"metadata": {"case:K-1": True}})
    assert seen[1] == ("POST", "/threads/search", {"metadata": {"case:K-1": True}, "limit": 20})
    assert seen[2][:2] == ("POST", "/threads/t1/history")
