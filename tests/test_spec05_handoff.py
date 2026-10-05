"""Spec 05 AC-21 and AC-22 (D-066: the api writes `handoff_emitted`): a turn from Platform whose handoff card is for
its own case appends one `handoff_emitted` `{handoff, handoff_reason?}` to the session's own case, once per trace,
also from the reconcile path; the console reads the card back unchanged; an escalated turn moves a `new` case to
`review` and leaves any other status alone. Offline: MemoryStore and the fake Platform of the spec 05 suite."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import demo
from app import fixtures as fx
from app.main import COOKIE, create_app
from tests.test_spec05_api import HTTPS, OTHER, SECRET, Env, bearer
from tests.test_spec05_guard import Dropping

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/mcp"))
from mcp_server.writes import call_open  # noqa: E402


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(demo, "new_run_id", lambda now: None)       # production-run sessions, as test_spec05_api
    return Env()


def turn(case_id, trace="tr-h1", reason="tool_failure", decision="escalate_unconfirmed_action", card=True) -> dict:
    """The graph's TurnResult for `case_id` with a handoff card for that case, as Platform streams it."""
    handoff = {**fx.HANDOFF, "case_id": case_id, "trace_id": trace, **({"handoff_reason": reason} if reason else {})}
    return {**fx.turn_result().model_dump(mode="json"), "case_id": case_id, "trace_id": trace, "decision": decision,
            "handoff": handoff if card else None}


def stream(env: Env) -> None:
    thread = env.client.post("/api/agent/threads").json()["thread_id"]
    assert env.client.post(f"/api/agent/threads/{thread}/runs/stream", json={}).status_code == 200


def handoffs(env: Env, case_id: str) -> list:
    return [e for e in env.store.events(case_id) if e.type == "handoff_emitted"]


def moves(env: Env, case_id: str) -> list[str]:
    return [e.payload["to"] for e in env.store.events(case_id) if e.type == "status_changed"]


def test_ac_21_a_turn_with_a_handoff_writes_one_event_with_the_card_unchanged(env):
    case_id = env.case()
    env.platform.turn = turn(case_id)
    env.login()
    stream(env)
    [event] = handoffs(env, case_id)
    assert event.payload == {"handoff": env.platform.turn["handoff"], "handoff_reason": "tool_failure"}
    assert (event.actor, event.trace_id, event.customer_visible) == ("agent", "tr-h1", False)


def test_ac_21_the_console_returns_the_card_the_graph_wrote(env):
    case_id = env.case()
    env.platform.turn = turn(case_id)
    env.login()
    stream(env)
    shown = env.client.get(f"/api/console/cases/{case_id}", headers=bearer()).json()
    assert shown["handoff"] == env.platform.turn["handoff"]
    mine = env.client.get(f"/api/cases/{case_id}")
    assert mine.status_code == 200 and "handoff" not in mine.json()                 # never in a customer view (D-013)
    assert all(e["type"] != "handoff_emitted" for e in mine.json()["timeline"])


def test_ac_21_the_same_trace_streamed_twice_writes_one_event(env):
    case_id = env.case()
    env.platform.turn = turn(case_id)
    env.login()
    stream(env)
    stream(env)
    assert len(handoffs(env, case_id)) == 1
    env.platform.turn = turn(case_id, trace="tr-h2")                                # a later turn: its own card
    stream(env)
    assert [e.trace_id for e in handoffs(env, case_id)] == ["tr-h1", "tr-h2"]


def test_ac_21_a_stream_without_a_turn_writes_the_handoff_from_the_thread_state(env):
    case_id = env.case()
    sid = env.login()
    thread = env.client.post("/api/agent/threads").json()["thread_id"]
    app = create_app(store=env.store, platform=Dropping(env.platform, turn(case_id, trace="tr-late")),
                     notifier=env.notifier, now=lambda: env.clock["t"])
    with TestClient(app, base_url=HTTPS) as browser:
        browser.cookies.set(COOKIE, sid)
        for _ in range(2):
            browser.post(f"/api/agent/threads/{thread}/runs/stream", json={})
    assert [e.trace_id for e in handoffs(env, case_id)] == ["tr-late"]


def test_ac_21_a_turn_without_case_id_or_card_writes_nothing(env):
    case_id = env.case()
    env.login()
    env.platform.turn = {**turn(case_id), "case_id": None}                          # a case get_case did not read back
    stream(env)
    env.platform.turn = turn(case_id, trace="tr-h2", card=False)
    stream(env)
    assert handoffs(env, case_id) == [] and moves(env, case_id) == []


@pytest.mark.parametrize("where", ["another customer", "another run"])
def test_ac_21_a_card_for_a_case_outside_the_session_writes_nothing(env, where):
    case_id = env.case(customer=OTHER) if where == "another customer" else env.case(run_id="demo-20260601T150000Z-ABCDEF")
    env.platform.turn = turn(case_id)
    env.login()
    stream(env)
    assert handoffs(env, case_id) == [] and moves(env, case_id) == []


def test_ac_21_a_person_requested_card_opens_the_mcp_call_hold(env):
    case_id = env.case()
    env.platform.turn = turn(case_id, reason="person_requested", decision="block_and_open_case")
    env.login()
    stream(env)
    assert call_open(env.store.events(case_id))                                     # spec 03 §8, D-055


@pytest.mark.parametrize("reason,decision", [("tool_failure", "escalate_unconfirmed_action"),
                                             (None, "escalate_unconfirmed_action"),
                                             ("person_requested", "block_and_open_case")])
def test_ac_22_an_escalated_turn_moves_a_new_case_to_review_once(env, reason, decision):
    case_id = env.case()
    env.platform.turn = turn(case_id, reason=reason, decision=decision)
    env.login()
    stream(env)
    stream(env)
    assert moves(env, case_id) == ["review"] and env.store.queue_status(case_id) == "review"
    assert env.notifier.sent == []                                                  # an agent move, as the MCP's


@pytest.mark.parametrize("before", ["verification", "review"])
def test_ac_22_a_case_already_moved_is_left_alone(env, before):
    case_id = env.case()
    env.store.change_status(case_id, before, on=fx.REPLAY_TODAY, actor="agent", trace_id="t")
    env.platform.turn = turn(case_id)
    env.login()
    stream(env)
    assert moves(env, case_id) == [before] and len(handoffs(env, case_id)) == 1


def test_ac_22_a_resolved_case_is_never_moved_back(env):
    case_id = env.case()
    env.resolve(case_id)
    env.platform.turn = turn(case_id)
    env.login()
    stream(env)
    assert env.store.queue_status(case_id) == "resolved" and moves(env, case_id)[-1] == "resolved"


def test_ac_22_a_turn_that_did_not_escalate_keeps_the_case_status(env):
    case_id = env.case()
    env.platform.turn = turn(case_id, reason="zone_medium", decision="handoff")
    env.login()
    stream(env)
    assert len(handoffs(env, case_id)) == 1 and moves(env, case_id) == []
