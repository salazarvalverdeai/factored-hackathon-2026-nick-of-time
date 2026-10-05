"""Spec 05 AC-23: a turn from Platform whose verified receipt is for its own case appends one customer-visible
`receipt_issued` `{receipt}` to the session's own case (the graph's dict, unchanged), once per trace, also from the
reconcile path; the customer case view shows it and its timeline lists it; the event notifies nobody. Offline:
MemoryStore and the fake Platform of the spec 05 suite."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import demo
from app import fixtures as fx
from app.main import COOKIE, create_app
from nick_of_time.contracts import CustomerReceipt, load_schema
from tests.test_spec05_api import HTTPS, OTHER, SECRET, Env
from tests.test_spec05_guard import Dropping

EXAMPLE = load_schema("customer_receipt.schema.json")["examples"][0]


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(demo, "new_run_id", lambda now: None)       # production-run sessions, as test_spec05_api
    return Env()


def turn(case_id, trace="tr-r1", receipt=True, turn_case=None) -> dict:
    """The graph's TurnResult with a receipt for `case_id`, as Platform streams it (no handoff card)."""
    return {**fx.turn_result().model_dump(mode="json"), "case_id": turn_case or case_id, "trace_id": trace,
            "receipt": {**EXAMPLE, "case_id": case_id} if receipt else None}


def stream(env: Env) -> None:
    thread = env.client.post("/api/agent/threads").json()["thread_id"]
    assert env.client.post(f"/api/agent/threads/{thread}/runs/stream", json={}).status_code == 200


def receipts(env: Env, case_id: str) -> list:
    return [e for e in env.store.events(case_id) if e.type == "receipt_issued"]


def test_ac_23_a_turn_with_a_receipt_writes_one_customer_visible_event_with_it_unchanged(env):
    case_id = env.case()
    env.platform.turn = turn(case_id)
    env.login()
    stream(env)
    [event] = receipts(env, case_id)
    assert event.payload == {"receipt": env.platform.turn["receipt"]}                 # exact match, constitution #5
    assert (event.actor, event.trace_id, event.customer_visible) == ("agent", "tr-r1", True)


def test_ac_23_the_customer_case_view_shows_the_receipt_and_lists_it_without_notifying(env):
    case_id = env.case()
    env.platform.turn = turn(case_id)
    env.login()
    stream(env)
    view = env.client.get(f"/api/cases/{case_id}").json()
    assert CustomerReceipt.model_validate(view["receipt"]) == CustomerReceipt.model_validate(env.platform.turn["receipt"])
    assert [e["label"] for e in view["timeline"] if e["type"] == "receipt_issued"] == ["Receipt issued"]
    assert env.notifier.sent == [] and env.store.list_notifications(fx.CUSTOMERS[0]["customer_id"], run_id=None) == []


def test_ac_23_the_same_trace_streamed_twice_writes_one_event(env):
    case_id = env.case()
    env.platform.turn = turn(case_id)
    env.login()
    stream(env)
    stream(env)
    assert len(receipts(env, case_id)) == 1
    env.platform.turn = turn(case_id, trace="tr-r2")
    stream(env)
    assert [e.trace_id for e in receipts(env, case_id)] == ["tr-r1", "tr-r2"]


def test_ac_23_a_stream_without_a_turn_writes_the_receipt_from_the_thread_state(env):
    case_id = env.case()
    sid = env.login()
    thread = env.client.post("/api/agent/threads").json()["thread_id"]
    app = create_app(store=env.store, platform=Dropping(env.platform, turn(case_id, trace="tr-late")),
                     notifier=env.notifier, now=lambda: env.clock["t"])
    with TestClient(app, base_url=HTTPS) as browser:
        browser.cookies.set(COOKIE, sid)
        for _ in range(2):
            browser.post(f"/api/agent/threads/{thread}/runs/stream", json={})
    assert [e.trace_id for e in receipts(env, case_id)] == ["tr-late"]


def test_ac_23_no_receipt_no_case_id_or_another_cases_receipt_writes_nothing(env):
    case_id, other = env.case(), env.case(transaction_id="TRX-FIXTURE0000000000002")
    env.login()
    for raw in ({**turn(case_id), "case_id": None}, turn(case_id, trace="tr-r2", receipt=False),
                turn(case_id, trace="tr-r3", turn_case=other)):               # a receipt for another case than the turn's
        env.platform.turn = raw
        stream(env)
    assert receipts(env, case_id) == [] and receipts(env, other) == []


@pytest.mark.parametrize("where", ["another customer", "another run"])
def test_ac_23_a_receipt_for_a_case_outside_the_session_writes_nothing(env, where):
    case_id = env.case(customer=OTHER) if where == "another customer" else env.case(run_id="demo-20260601T150000Z-ABCDEF")
    env.platform.turn = turn(case_id)
    env.login()
    stream(env)
    assert receipts(env, case_id) == []
