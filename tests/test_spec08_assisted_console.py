"""Spec 08 AC-10 to AC-15: the assisted console's api (`app/console.py`): case context, summary, deadline, audit
checklist and the copilot proposal in plain words; spec 18 AC-09 and AC-11 for the second opinion (T5).

Offline: MemoryStore, the fixture catalog, the spec 05 Cognito test key and `fake` LLM clients (never a real model).
"""
from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app import demo
from app import fixtures as fx
from app.auth import CognitoVerifier
from app.catalog import FixtureCatalog
from app.main import create_app
from nick_of_time import ids, llm
from nick_of_time.contracts import AnalystActionIn
from nick_of_time.policy.clock import deadline
from nick_of_time.receipt import build
from nick_of_time.store import NewCase
from nick_of_time.store.memory import MemoryStore
from tests.test_spec05_api import CLIENT, HTTPS, ISS, JWK, ME, OTHER, START, FakeNotifier, FakePlatform, bearer

PRICES = {"input_per_1m": 1.0, "output_per_1m": 5.0}     # [simulated] a price row so the fake calls are billed
DEMO_RUN, OTHER_RUN = "demo-20260601T150000Z-ABCDEF", "demo-20260601T150000Z-GHIJKL"
OTHER_TRX = "TRX-FIXTURE0000000000002"
CLOCK = deadline("MX", "debit", dt.date(2026, 6, 1), charged_at=dt.date(2026, 5, 31))
FACTS = dict(customer_id=ME, transaction_id=fx.TRANSACTION_ID, product_id=fx.PRODUCT_ID, country="MX",
             product_type="debit", zone="high", dispute_type="unrecognized_charge", opened_on=dt.date(2026, 6, 1),
             credit_deadline=CLOCK.credit_deadline, ruling_deadline=CLOCK.ruling_deadline,
             deadline_source=CLOCK.deadline_source, deadline_source_url=CLOCK.source_url,
             deadline_verified_on=CLOCK.verified_on, mode="replay", trace_id="trace-1")
PATHS = ("context", "summary", "audit", "second-opinion")


def judged(verdict="agree") -> dict:
    return {"verdict": verdict, "questions": [],
            "reasons": [{"text": f"The charge {fx.TRANSACTION_ID} was blocked and verified.",
                         "evidence_ids": [fx.TRANSACTION_ID]}]}


class Env:
    def __init__(self, judge_script=None, summary_script=None, platform=None):
        self.clock = {"t": START}
        self.store = MemoryStore(now=lambda: self.clock["t"])
        self.judge = llm.FakeClient("fake-judge", prices=PRICES, script=judge_script)
        self.writer = llm.FakeClient("fake-writer", prices=PRICES, script=summary_script)
        self.platform = platform(self.clock) if platform else FakePlatform()
        self.app = create_app(store=self.store, verifier=CognitoVerifier(issuer=ISS, client_id=CLIENT,
                                                                         jwks={"keys": [JWK]}),
                              platform=self.platform, notifier=FakeNotifier(), now=lambda: self.clock["t"],
                              link_key="k", judge_llm=self.judge, summary_llm=self.writer)
        self.client = TestClient(self.app, base_url=HTTPS)

    def case(self, run_id=None, **changes):
        return self.store.create_case(NewCase(**{**FACTS, "run_id": run_id, **changes}), actor="agent",
                                      action_id=ids.new_id("action"))

    def verified_case(self, run_id=None, zone="high", score=87.0, **card):
        """A case the agent opened and blocked, both verified by their reads, with its handoff card (spec 05 AC-21)."""
        c = self.case(run_id=run_id, zone=zone)
        opened = self.store.record_verification(c.case_id, c.action_id, read="get_case", run_id=run_id,
                                                customer_id=None, actor="agent", trace_id="tr-1")
        block = ids.new_id("action")
        self.store.block_product(c.case_id, fx.PRODUCT_ID, action_id=block, actor="agent", trace_id="tr-1")
        blocked = self.store.record_verification(c.case_id, block, read="get_product_status", run_id=run_id,
                                                 customer_id=None, actor="agent", trace_id="tr-1")
        v_open, v_block = opened.payload["verification_id"], blocked.payload["verification_id"]
        handoff = {
            "case_id": c.case_id, "language": "es", "zone": zone,
            "request": "unrecognized_charge · USD 1250.00 on 2026-05-31 · TIENDA X",
            "verified_facts": [{"fact": "unrecognized_charge: USD 1250.00 on 2026-05-31",
                                "source_id": fx.TRANSACTION_ID}],
            "actions": [{"tool": "open_case", "action_id": c.action_id, "result": "verified", "verified": True,
                         "verification_id": v_open},
                        {"tool": "block_card", "action_id": block, "result": "verified", "verified": True,
                         "verification_id": v_block}],
            "evidence": [fx.TRANSACTION_ID, fx.PRODUCT_ID, c.case_id, c.action_id, block, v_open, v_block],
            "open_questions": [], "trace_id": "tr-1",
            "deadline": {"country": "MX", "product": "debit", "credit_deadline": str(CLOCK.credit_deadline),
                         "ruling_deadline": str(CLOCK.ruling_deadline), "deadline_source": CLOCK.deadline_source,
                         "source_url": CLOCK.source_url, "verified_on": str(CLOCK.verified_on)},
            "score": score, "score_source": "dataset", "score_version": "gold-v1", "guardrails_triggered": [],
            **card}
        self.store.append_event(c.case_id, "handoff_emitted", actor="agent", trace_id="tr-1",
                                payload={"handoff": handoff})
        return c, handoff

    def get(self, case_id, path, **kw):
        return self.client.get(f"/api/console/cases/{case_id}/{path}", headers=bearer(**kw))


@pytest.fixture(autouse=True)
def production_runs(monkeypatch):
    monkeypatch.setattr(demo, "new_run_id", lambda now: None)


def state(env: Env, case_id: str):
    return [(e.type, e.payload) for e in env.store.events(case_id)], env.store.queue_status(case_id)


# ---------- AC-15 auth ----------
@pytest.mark.parametrize("path", PATHS)
def test_ac_15_every_assisted_route_needs_the_analyst_token(path):
    env = Env()
    c, _ = env.verified_case()
    assert env.client.get(f"/api/console/cases/{c.case_id}/{path}").status_code == 401
    bad = env.client.get(f"/api/console/cases/{c.case_id}/{path}", headers={"Authorization": "Bearer forged"})
    assert bad.status_code == 401
    assert env.get(c.case_id, path).status_code == 200


def test_ac_15_the_post_needs_the_token_and_an_unknown_or_eval_case_is_404():
    env = Env(judge_script=[judged()])
    c, _ = env.verified_case()
    assert env.client.post(f"/api/console/cases/{c.case_id}/second-opinion").status_code == 401
    assert env.judge.calls == []
    hidden = env.case(run_id="eval-run-1").case_id                              # eval runs never reach the console
    for path in PATHS:
        assert env.get("K-999999", path).status_code == 404
        assert env.get(hidden, path).status_code == 404


# ---------- AC-10 context ----------
def test_ac_10_context_lists_the_customer_cases_cards_charges_calls_and_notifications():
    env = Env()
    old = env.case(transaction_id=OTHER_TRX)
    env.store.change_status(old.case_id, "review", on=dt.date(2026, 6, 1), actor="agent", trace_id="t")
    for action, to in (("take", None), ("approve_credit", None), ("resolve", "resolved")):
        env.store.record_analyst_action(AnalystActionIn(case_id=old.case_id, actor_id="ana", action=action,
                                                        reason="ok", idempotency_key=action),
                                        new_status=to, on=dt.date(2026, 6, 1), trace_id="t")
    c, _ = env.verified_case()
    env.store.append_event(c.case_id, "call_requested", actor="customer", trace_id="t",
                           payload={"action_id": ids.new_id("action"), "preferred_time": None,
                                    "expected_contact_by": "2026-06-02"})
    note = env.store.add_notification(c.case_id, event="case_opened", channel="log", masked_address=None,
                                      text="Abrimos tu caso.", trigger="auto", actor="system", trace_id="t")
    env.store.add_delivery(note.notification_id, "delivered")
    body = env.get(c.case_id, "context").json()
    assert body["previous_cases"] == [{"case_id": old.case_id, "opened_at": old.created_at.isoformat(),
                                       "status": "resolved", "outcome": "approve_credit"}]
    [txn] = body["transactions"]
    assert txn == {"transaction_id": fx.TRANSACTION_ID, "date": "2026-05-31", "amount": 1250.0, "currency": "USD",
                   "merchant": "TIENDA X", "last4": "4417", "disputed": True, "synthetic": False}
    assert body["cards"] == [{"product_id": fx.PRODUCT_ID, "last4": "4417", "product": "debit", "status": "Blocked"}]
    [call] = body["calls"]
    assert (call["status"], call["case_id"], call["expected_contact_by"]) == ("requested", c.case_id, "2026-06-02")
    assert [(n["channel"], n["event"], n["status"]) for n in body["notifications"]] == [
        ("log", "case_opened", "delivered")]


def test_ac_10_context_keeps_to_the_case_run():
    env = Env()
    mine = env.case(run_id=DEMO_RUN)
    same_run = env.case(run_id=DEMO_RUN, transaction_id=OTHER_TRX)
    env.case(run_id=OTHER_RUN, transaction_id=OTHER_TRX)                      # another visitor's run
    env.case(run_id=None, transaction_id=OTHER_TRX)                           # production
    env.case(run_id=DEMO_RUN, customer_id=OTHER, transaction_id=OTHER_TRX)    # another customer
    other_note = env.store.add_notification(env.case(run_id=OTHER_RUN).case_id, event="case_opened", channel="log",
                                            masked_address=None, text="x", trigger="auto", actor="system",
                                            trace_id="t")
    body = env.get(mine.case_id, "context").json()
    assert [p["case_id"] for p in body["previous_cases"]] == [same_run.case_id]
    assert all(n["case_id"] != other_note.case_id for n in body["notifications"])
    assert body["cards"][0]["status"] == "Active"                             # no block in this run


def test_ac_10_the_window_is_thirty_days_around_the_charge_up_to_the_business_today(monkeypatch):
    env = Env()
    c = env.case()
    seen = {}

    def between(self, customer_id, start, end, limit):
        seen.update(customer_id=customer_id, start=start, end=end)
        return []
    monkeypatch.setattr(FixtureCatalog, "transactions_between", between)
    body = env.get(c.case_id, "context").json()
    assert seen == {"customer_id": ME, "start": dt.date(2026, 5, 1), "end": dt.date(2026, 6, 1)}
    assert [t["disputed"] for t in body["transactions"]] == [True]            # the disputed charge is always there


# ---------- AC-11 summary ----------
def test_ac_11_template_summary_states_report_verified_actions_decision_and_deadline():
    env = Env()
    c, handoff = env.verified_case()
    body = env.get(c.case_id, "summary").json()
    assert body["writer"] == "template" and env.writer.calls == []
    lines = body["lines"]
    assert lines[0] == "El cliente reporta un cargo no reconocido: USD 1250.00 del 2026-05-31 en TIENDA X."
    assert sum(line.startswith("Hecho y verificado") for line in lines) == 2
    assert any(line.startswith("Plazo legal") and str(CLOCK.credit_deadline) in line for line in lines)
    facts = [handoff, FixtureCatalog().transaction(fx.TRANSACTION_ID),
             env.store.get_case(c.case_id, run_id=None, customer_id=None).model_dump(mode="json")]
    assert not any(build.bad(line, facts) for line in lines)                  # every number, date and id grounded
    assert body["deadline"] == {"kind": "credit", "date": str(CLOCK.credit_deadline),
                                "days_left": (CLOCK.credit_deadline - dt.date(2026, 6, 1)).days,
                                "source_label": CLOCK.deadline_source, "source_url": CLOCK.source_url}


def test_ac_11_unverified_actions_are_never_told_as_done():
    env = Env()
    c, handoff = env.verified_case()
    assert sum(x.startswith("Hecho y verificado") for x in env.get(c.case_id, "summary").json()["lines"]) == 2
    later = {**handoff, "trace_id": "tr-2", "actions": [
        {k: v for k, v in a.items() if k != "verification_id"} | {"verified": False, "result": "not_confirmed"}
        for a in handoff["actions"]]}
    env.store.append_event(c.case_id, "handoff_emitted", actor="agent", trace_id="tr-2", payload={"handoff": later})
    lines = env.get(c.case_id, "summary").json()["lines"]                    # a new handoff version: rebuilt
    assert not any(line.startswith("Hecho y verificado") for line in lines)
    assert "El agente no tiene acciones verificadas en este caso." in lines
    assert sum(line.startswith("Sin confirmar") for line in lines) == 2


def test_ac_11_no_legal_deadline_gives_null_and_no_invented_date():
    env = Env()
    c = env.case(country="AR", credit_deadline=None, ruling_deadline=None, deadline_source=None,
                 deadline_source_url=None, deadline_verified_on=None)
    body = env.get(c.case_id, "summary").json()
    assert body["deadline"] is None
    assert body["lines"][-1].startswith("Sin plazo legal verificado")


def test_ac_11_llm_wording_keeps_grounded_lines_and_falls_back_on_the_rest():
    env = Env(summary_script=["[1] Reporte: cargo no reconocido de USD 9999.00 en TIENDA X.\n"
                              "[2,3] El caso y el bloqueo quedaron verificados.\n"])
    env.store.record_setting("writer", "llm", actor="analyst:ana")
    c, _ = env.verified_case()
    body = env.get(c.case_id, "summary").json()
    assert body["writer"] == "llm" and len(env.writer.calls) == 1
    lines = body["lines"]
    assert "9999" not in " ".join(lines)                                      # an ungrounded amount never leaves
    assert lines[0].startswith("El cliente reporta un cargo no reconocido: USD 1250.00")   # its template line
    assert "El caso y el bloqueo quedaron verificados." in lines
    assert any(line.startswith("Plazo legal") for line in lines)               # uncovered lines are appended
    [row] = env.store.list_llm_calls(run_id=None)
    assert row.trace_id.startswith("console-summary-") and row.model == "fake-writer"
    again = env.get(c.case_id, "summary").json()                               # cached per case + handoff version
    assert again["lines"] == lines and len(env.writer.calls) == 1


def test_ac_11_any_writer_failure_or_the_daily_cap_gives_the_template():
    env = Env(summary_script=[llm.ProviderUnavailable("down")])
    env.store.record_setting("writer", "llm", actor="analyst:ana")
    c, _ = env.verified_case()
    body = env.get(c.case_id, "summary").json()
    assert body["writer"] == "template" and body["lines"][0].startswith("El cliente reporta")
    capped = Env(summary_script=["[1] x"])
    capped.store.record_setting("writer", "llm", actor="analyst:ana")
    capped.store.add_llm_call(trace_id="t", provider="fake", model="m", tokens_in=1, tokens_out=1, latency_ms=1,
                              cost_usd=5, run_id=None)
    c2, _ = capped.verified_case()
    assert capped.get(c2.case_id, "summary").json()["writer"] == "template"
    assert capped.writer.calls == []


# ---------- AC-12 second opinion (spec 18 AC-09, AC-11, T5) ----------
def test_ac_12_second_opinion_is_advisory_logged_and_changes_nothing():
    env = Env(judge_script=[judged()])
    c, _ = env.verified_case()
    before = state(env, c.case_id)
    assert env.get(c.case_id, "second-opinion").json()["available"] is False
    got = env.client.post(f"/api/console/cases/{c.case_id}/second-opinion", headers=bearer())
    assert got.status_code == 200
    body = got.json()
    assert body["available"] is True and body["verdict"] == "agree"
    assert body["label"] == "model opinion (advisory)" and body["model"] == "fake-judge"
    assert body["reasons"] == [{"text": f"The charge {fx.TRANSACTION_ID} was blocked and verified.",
                                "evidence_ids": [fx.TRANSACTION_ID]}]
    assert state(env, c.case_id) == before                                     # spec 18 AC-09: no event, no status
    [row] = env.store.list_llm_calls(run_id=None)
    assert row.trace_id.startswith("judge-") and row.cost_usd > 0
    assert env.get(c.case_id, "second-opinion").json() == body                 # GET returns the latest
    assert env.client.post(f"/api/console/cases/{c.case_id}/second-opinion", headers=bearer()).json() == body
    assert len(env.judge.calls) == 1                                           # one call per handoff version


def test_ac_12_the_daily_cap_is_respected_before_the_call():
    env = Env(judge_script=[judged()])
    env.store.add_llm_call(trace_id="t", provider="fake", model="m", tokens_in=1, tokens_out=1, latency_ms=1,
                           cost_usd=4.995, run_id=None)
    c, _ = env.verified_case()
    body = env.client.post(f"/api/console/cases/{c.case_id}/second-opinion", headers=bearer()).json()
    assert (body["available"], body["reason"], body["verdict"]) == (False, "budget", None)
    assert env.judge.calls == [] and len(env.store.list_llm_calls(run_id=None)) == 1


def test_ac_12_a_failing_judge_or_no_card_is_no_second_opinion():
    env = Env(judge_script=[llm.ProviderUnavailable("down")])
    c, _ = env.verified_case()
    before = state(env, c.case_id)
    body = env.client.post(f"/api/console/cases/{c.case_id}/second-opinion", headers=bearer()).json()
    assert (body["available"], body["reason"]) == (False, "error") and state(env, c.case_id) == before
    bare = env.case(transaction_id=OTHER_TRX)
    body = env.client.post(f"/api/console/cases/{bare.case_id}/second-opinion", headers=bearer()).json()
    assert (body["available"], body["reason"]) == (False, "no_handoff")


def test_ac_12_ungrounded_reasons_are_dropped_and_the_verdict_becomes_uncertain():
    wrong = {"verdict": "disagree", "questions": [],
             "reasons": [{"text": "The customer has 4321 prior disputes.", "evidence_ids": [fx.TRANSACTION_ID]}]}
    env = Env(judge_script=[wrong])
    c, _ = env.verified_case()
    body = env.client.post(f"/api/console/cases/{c.case_id}/second-opinion", headers=bearer()).json()
    assert (body["verdict"], body["reasons"]) == ("uncertain", [])


# ---------- AC-13 audit ----------
def test_ac_13_audit_checklist_on_a_clean_case_matches():
    env = Env()
    c, _ = env.verified_case()
    before = state(env, c.case_id)
    body = env.get(c.case_id, "audit").json()
    by_id = {x["id"]: x for x in body["checks"]}
    assert list(by_id) == ["A1", "A2", "A3", "A4", "A5", "A6", "A7"]
    assert all(set(x) >= {"id", "name", "passed", "detail", "status"} for x in body["checks"])
    assert [by_id[k]["passed"] for k in ("A1", "A2", "A3", "A6", "A7")] == [True] * 5
    assert by_id["A4"]["status"] == by_id["A5"]["status"] == "not_applicable" and by_id["A4"]["passed"] is None
    assert body["matches"] is True
    assert body["rederived_outcome"] == {"zone": "high", "credit_deadline": str(CLOCK.credit_deadline),
                                         "ruling_deadline": str(CLOCK.ruling_deadline),
                                         "deadline_source": CLOCK.deadline_source}
    assert state(env, c.case_id) == before


def test_ac_13_audit_flags_a_zone_or_deadline_that_does_not_re_derive():
    env = Env()
    c, _ = env.verified_case(zone="human", score=87.0)                      # 87 is the high zone
    body = env.get(c.case_id, "audit").json()
    a1 = next(x for x in body["checks"] if x["id"] == "A1")
    assert (a1["passed"], a1["status"], body["matches"]) == (False, "finding", False)
    late = env.case(credit_deadline=dt.date(2026, 7, 1), transaction_id=fx.TRANSACTION_ID, run_id=DEMO_RUN)
    body = env.get(late.case_id, "audit").json()
    a2 = next(x for x in body["checks"] if x["id"] == "A2")
    assert (a2["passed"], a2["severity"], body["matches"]) == (False, "critical", False)
    assert body["rederived_outcome"]["credit_deadline"] == str(CLOCK.credit_deadline)


# ---------- AC-14 proposal in plain words ----------
@pytest.mark.parametrize("zone, score, action, why", [
    ("medium", 40.0, "approve_block", "la zona es media"),
    ("human", None, "request_customer_info", "no hay puntaje de fraude del banco"),
])
def test_ac_14_the_proposal_carries_a_plain_explanation(zone, score, action, why):
    env = Env()
    proposal = {"action": action, "rationale": "x", "requires_human": True}
    c, handoff = env.verified_case(zone=zone, score=score, copilot_proposal=proposal)
    body = env.client.get(f"/api/console/cases/{c.case_id}", headers=bearer()).json()
    assert body["handoff"] == handoff                                         # the card stays as the graph wrote it
    assert body["proposal"]["action"] == action and body["proposal"]["requires_human"] is True
    assert body["proposal"]["explanation"].startswith("Sugerencia: ") and why in body["proposal"]["explanation"]
    assert ", porque " in body["proposal"]["explanation"]


def test_ac_14_no_proposal_no_explanation():
    env = Env()
    c, _ = env.verified_case()
    assert env.client.get(f"/api/console/cases/{c.case_id}", headers=bearer()).json()["proposal"] is None
