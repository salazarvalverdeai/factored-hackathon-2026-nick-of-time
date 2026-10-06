"""Spec 18 T5 through the api: the console's second opinion (`POST/GET /api/console/cases/{id}/second-opinion`) is
labeled advisory and never changes state (AC-09); a failing, timed-out or over-budget judge is "No second opinion" and
nothing else changes (AC-11). Offline: the spec 08 assisted-console harness with `fake` LLM clients."""
from __future__ import annotations

import threading

from nick_of_time import llm
from nick_of_time.audit import judge
from tests.test_spec05_api import bearer
from tests.test_spec08_assisted_console import Env, judged, state


def post(env: Env, case_id: str) -> dict:
    got = env.client.post(f"/api/console/cases/{case_id}/second-opinion", headers=bearer())
    assert got.status_code == 200
    return got.json()


def test_ac_09_the_console_opinion_is_labeled_advisory_and_changes_no_state():
    env = Env(judge_script=[judged("disagree")])
    c, _ = env.verified_case()
    before = state(env, c.case_id)
    body = post(env, c.case_id)
    assert (body["verdict"], body["label"]) == ("disagree", "model opinion (advisory)")
    assert state(env, c.case_id) == before                                     # no event, no status, no block
    assert env.store.list_notifications(c.customer_id, run_id=None) == []       # never reaches the customer
    [call] = env.judge.calls
    assert call["temperature"] == 0 and call["tool_name"] == "second_opinion"


def test_ac_11_budget_failure_and_timeout_give_no_second_opinion(monkeypatch):
    capped = Env(judge_script=[judged()])
    capped.store.add_llm_call(trace_id="t", provider="fake", model="m", tokens_in=1, tokens_out=1, latency_ms=1,
                              cost_usd=5, run_id=None)
    c, _ = capped.verified_case()
    assert post(capped, c.case_id)["reason"] == "budget" and capped.judge.calls == []

    failing = Env(judge_script=[llm.ProviderUnavailable("down")])
    c, _ = failing.verified_case()
    before = state(failing, c.case_id)
    body = post(failing, c.case_id)
    assert (body["available"], body["verdict"], body["reasons"]) == (False, None, [])
    assert state(failing, c.case_id) == before

    release = threading.Event()

    class Slow(llm.FakeClient):
        def _call(self, *args):
            release.wait(2)
            return super()._call(*args)

    slow = Env()
    slow.judge.__class__ = Slow
    slow.judge.script = [judged()]
    original = judge.opinion
    monkeypatch.setattr(judge, "opinion", lambda *a, **kw: original(*a, **{**kw, "timeout_s": 0.05}))
    c, _ = slow.verified_case()
    body = post(slow, c.case_id)
    release.set()
    assert (body["available"], body["reason"]) == (False, "timeout")
