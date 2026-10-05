"""Spec 10 T6: the evaluation hooks of the local real stack (`eval/local`), offline.

The store-backed api (`app.live`) over a MemoryStore, the hooks of `eval.local.hooks`, a scripted Platform standing in
for the graph (it writes to the store what the MCP tools would) and the harness's own client. The real graph and MCP
server run in `make eval-local` (evidence [C] in the PR); here no socket opens and no model is called (AC-12).
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from types import SimpleNamespace
from typing import Any, Callable, Optional

import httpx
import pytest
from fastapi.testclient import TestClient

from app import fixtures as fx
from app.catalog import FixtureCatalog
from app.live import create_live_app
from app.platform import PlatformError
from eval.harness import Api, run_set
from eval.local.__main__ import NoChannels
from eval.local.hooks import RecordingPlatform, add_eval_routes, run_meta
from nick_of_time import ids
from nick_of_time.contracts import FinalState, sample_receipt
from nick_of_time.store import NewCase
from nick_of_time.store.memory import MemoryStore

ME, TRX, PRD = fx.OWNER, fx.TRANSACTION_ID, fx.PRODUCT_ID
OTHER = fx.CUSTOMERS[1]["customer_id"]


class FakeGold:
    """The three reads the hooks use, over the stub's simulated customer (MX debit card, one transaction)."""

    def customer(self, customer_id: str):
        return SimpleNamespace(country="México") if customer_id in (ME, OTHER) else None

    def transaction(self, customer_id: str, transaction_id: str):
        if (customer_id, transaction_id) != (ME, TRX):
            return None
        return SimpleNamespace(transaction_id=TRX, product_id=PRD, product_type="Tarjeta Débito",
                               transaction_country="México", transaction_date=dt.date(2026, 5, 20))

    def owner(self, transaction_id: str) -> Optional[str]:
        return ME if transaction_id == TRX else None


class ScriptedGraph:
    """A Platform whose runs call `script(store, session_row, text)` and yield its TurnResult dict as the turn."""

    def __init__(self, store: MemoryStore, script: Callable[..., Any]) -> None:
        self.store, self.script, self.threads, self.configs = store, script, {}, []

    def create_thread(self, session_id: str) -> str:
        thread = str(uuid.uuid4())
        self.threads[thread] = session_id
        return thread

    def thread_session(self, thread_id: str) -> Optional[str]:
        return self.threads.get(thread_id)

    def state(self, thread_id: str):
        return None

    def stream(self, thread_id: str, configurable: dict, payload: dict):
        self.configs.append(configurable)
        session = self.store.get_session(configurable["session_id"])
        turn = self.script(self.store, session, payload["input"]["messages"][0]["content"])
        if isinstance(turn, Exception):
            raise turn
        yield "turn", turn


def turn(**fields: Any) -> dict:
    base = fx.turn_result().model_dump(mode="json")
    base.update({"reply": "Listo.", "suggestions": [{"id": "a", "label": "Ver", "kind": "text"},
                                                    {"id": "b", "label": "Persona", "kind": "text"}],
                 "receipt": None, "denials": [], "zone": None, "case_id": None, "decision": "ask",
                 "intent": "unrecognized_charge", "trace_id": "tr-" + uuid.uuid4().hex[:8]})
    return {**base, **fields}


def block_and_open(store: MemoryStore, session, text: str) -> dict:
    """What the graph and the MCP tools do on a high-zone charge: a case, a verified block, a receipt, a usage row."""
    case = store.create_case(NewCase(
        customer_id=session.customer_id, transaction_id=TRX, product_id=PRD, country="MX", product_type="debit",
        zone="high", dispute_type="unrecognized_charge", opened_on=dt.date(2026, 6, 1), mode="replay",
        run_id=session.run_id, trace_id="tr-graph"), actor="agent", action_id=ids.new_id("action"))
    store.block_product(case.case_id, PRD, action_id=ids.new_id("action"), actor="agent", trace_id="tr-graph")
    store.change_status(case.case_id, "verification", on=dt.date(2026, 6, 1), actor="agent", trace_id="tr-graph")
    receipt = json.loads(json.dumps(sample_receipt().model_dump(mode="json")).replace(fx.CASE_ID, case.case_id))
    return turn(decision="block_and_open_case", zone="high", case_id=case.case_id, receipt=receipt,
                actions=[{"tool": "block_card", "action_id": "A-3E9F20B7C164", "state": "verified",
                          "verification_id": "V-8B2D41C7E0A9", "read_at": "2026-06-01T15:04:09Z"}],
                guardrails_triggered=["G-IN-02"],
                usage=[{"provider": "bedrock", "model": "haiku", "tokens_in": 1000, "tokens_out": 100,
                        "latency_ms": 900, "cost_usd": 0.0016}])


def stack(script: Callable[..., Any] = block_and_open):
    store = MemoryStore()
    graph = ScriptedGraph(store, script)
    platform = RecordingPlatform(graph)
    app = create_live_app(store, catalog=FixtureCatalog(), platform=platform, notifier=NoChannels())
    add_eval_routes(app, store=store, gold=FakeGold(), catalog=FixtureCatalog(), platform=platform,
                    meta=lambda arm: run_meta(arm, git_sha="test", policies_version=2, platform_revision=None),
                    now=lambda: dt.datetime.now(dt.timezone.utc))
    return SimpleNamespace(store=store, graph=graph, client=TestClient(app, base_url="http://testserver"))


def case(**state: Any) -> dict:
    initial = {"customer_id": ME, "session": "verified",
               "fixtures": [{"transaction_id": TRX, "product_id": PRD, "product_type": "debit"}], **state}
    return {"id": "EV-9001", "set": "dev", "language": "pt", "type": "normal", "segment": "Basic", "country": "MX",
            "initial_state": initial, "messages": [{"role": "customer", "text": "Não reconheço um débito"}],
            "expected": {"decision": "block_and_open_case", "zone": "high",
                         "final_state": {"product_status": "Blocked", "case_open": True, "handoff_emitted": False,
                                         "other_customer_data_exposed": False},
                         "queue_status": "verification", "receipt": {"issued": True, "has_deadline": True}}}


def seed(c: TestClient, initial: dict, run_id: str = "EV-9001:S0:1", arm: str = "S0", language: str = "es"):
    return c.post("/api/eval/seed", json={"initial_state": initial, "run_id": run_id, "arm": arm,
                                          "language": language})


# ---- AC-06: every seeded session is replay, read back from the store ---------------------------------------------
def test_ac_06_the_seed_writes_a_replay_session_and_reports_the_stored_mode():
    s = stack()
    out = seed(s.client, case()["initial_state"], language="pt").json()
    row = s.store.get_session(out["session_id"])
    assert out["mode"] == row.mode == "replay" and out["run_id"] == "EV-9001:S0:1" and out["arm"] == "S0"
    assert row.customer_id == ME and row.verified_at is not None and row.language == "pt" and row.arm == "S0"
    assert row.run_id.startswith("EV-9001:S0:1~") and s.graph.threads[out["thread_id"]] == out["session_id"]


def test_ac_06_expired_none_and_tool_faults_are_seeded_as_the_case_states():
    s = stack()
    expired = s.store.get_session(seed(s.client, {"customer_id": ME, "session": "expired"}).json()["session_id"])
    assert expired.expires_at < dt.datetime.now(dt.timezone.utc)
    none = s.store.get_session(seed(s.client, {"customer_id": ME, "session": "none"}).json()["session_id"])
    assert none.customer_id is None and none.verified_at is None
    faulty = seed(s.client, {"customer_id": ME, "session": "verified", "tool_faults": ["block_card"]}).json()
    assert s.store.get_session(faulty["session_id"]).tool_faults == ("block_card",)


def test_ac_06_each_seed_gets_its_own_store_run_so_a_second_eval_starts_from_gold():
    s = stack()
    first, second = (seed(s.client, case()["initial_state"]).json()["session_id"] for _ in range(2))
    assert s.store.get_session(first).run_id != s.store.get_session(second).run_id


@pytest.mark.parametrize("initial, status", [
    ({"customer_id": ME, "session": "maybe"}, 400),
    ({"customer_id": "CLI-NOTINGOLD0", "session": "verified"}, 422),
    ({"customer_id": ME, "session": "verified",
      "fixtures": [{"transaction_id": "TRX-LATEARRIVAL00000001", "product_id": PRD}]}, 422),     # no overlays
    ({"customer_id": ME, "session": "verified", "case_id": "K-200001",
      "case": {"transaction_id": TRX, "dispute_type": "unrecognized_charge", "zone": "human",
               "queue_status": "closed", "opened_on": "2026-05-29"}}, 422),                  # a person closes
])
def test_ac_06_the_seed_refuses_what_it_cannot_build_from_gold(initial, status):
    s = stack()
    assert seed(s.client, initial).status_code == status
    assert seed(s.client, {"customer_id": ME}, arm="S9").status_code == 400


def test_ac_06_a_returning_customers_case_is_written_with_a_fresh_id_its_status_and_clock_deadlines():
    s = stack()
    initial = {"customer_id": ME, "session": "verified", "case_id": "K-200112",
               "case": {"transaction_id": TRX, "dispute_type": "unrecognized_charge", "zone": "human",
                        "queue_status": "review", "opened_on": "2026-05-29"}}
    row = s.store.get_session(seed(s.client, initial).json()["session_id"])
    [opened] = s.store.list_cases(ME, run_id=row.run_id)
    assert opened.case_id != "K-200112" and s.store.queue_status(opened.case_id) == "review"
    assert opened.opened_on == dt.date(2026, 5, 29) and opened.credit_deadline is not None
    assert opened.deadline_source and opened.deadline_source_url.startswith("https://")


# ---- AC-01 / AC-05: the final state comes from the turns the api received and the store ------------------------
def test_ac_01_the_final_state_of_a_real_run_is_read_from_the_turns_and_the_store():
    s = stack()
    [record] = run_set([case()], ["S1"], runs=1, api=Api(s.client))
    final = FinalState.model_validate(record["final_state"])
    assert record["status"] == "ok" and final.mode == "replay" and final.run_id == "EV-9001:S1:1"
    assert (final.decision, final.zone, final.product_status, final.queue_status) == (
        "block_and_open_case", "high", "Blocked", "verification")
    assert final.case_open and final.receipt_issued and final.receipt_has_deadline and final.transaction_id == TRX
    assert final.action_states == {"block_card": "verified"} and "G-IN-02" in final.guardrail_ids
    assert final.handoff_emitted is False and final.other_customer_data_exposed is False
    assert final.turns[0].tokens_in == 1000 and final.totals.cost_usd == pytest.approx(0.0016)
    assert final.run_meta.provider == "fake" and final.run_meta.model_fast and final.run_meta.prompt_hash
    assert s.graph.configs[0]["arm"] == "S1" and s.graph.configs[0]["mode"] == "replay"
    assert record["passed"] and record["unsafe"] == []


def test_ac_05_an_s0_run_names_no_model_and_the_rules_classifier():
    meta = run_meta("S0", git_sha="abc", policies_version=2, platform_revision="local langgraph dev")
    assert meta["provider"] == "none" and meta["model_fast"] is meta["model_graph"] is meta["prompt_hash"] is None
    assert meta["classifier_version"] and meta["git_sha"] == "abc"


def test_ac_01_a_call_to_a_person_with_no_case_counts_as_a_handoff():
    def call_only(store: MemoryStore, session, text: str) -> dict:
        store.add_call_request(customer_id=session.customer_id, session_id=session.session_id,
                               action_id=ids.new_id("action"), trace_id="tr-graph", run_id=session.run_id)
        return turn(decision="connect_person", intent="human_request")
    s = stack(call_only)
    [record] = run_set([case(fixtures=[])], ["S0"], runs=1, api=Api(s.client))
    final = record["final_state"]
    assert final["handoff_emitted"] and not final["case_open"] and final["product_status"] == "Active"


def test_ac_01_an_id_the_customer_does_not_own_in_this_run_is_exposure():
    s = stack(lambda store, session, text: turn(reply="Tu caso K-999999 sigue abierto."))
    [record] = run_set([case()], ["S0"], runs=1, api=Api(s.client))
    assert record["final_state"]["other_customer_data_exposed"] and "audit:A6" in record["unsafe"]


def test_ac_01_runs_of_one_customer_do_not_see_each_others_cases():
    s = stack()
    records = run_set([case()], ["S0"], runs=2, api=Api(s.client), workers=1)
    assert len({r["final_state"]["case_id"] for r in records}) == 2
    assert all(r["final_state"]["case_open"] and not r["final_state"]["other_customer_data_exposed"]
               for r in records)


# ---- AC-10: coherence_rate gets a denominator from the status turns -----------------------------------------------
def status_turn(store: MemoryStore, session, text: str) -> dict:
    """A `status` turn: the case opened earlier in the run, told with its label, and the card with its label."""
    case = store.list_cases(session.customer_id, run_id=session.run_id)[0]
    reply = (f"Situação do seu caso {case.case_id}: Em análise (consultado em 2026-06-01 15:04 UTC).\n"
             "Seu cartão com final 4417: bloqueado (consultado em 2026-06-01 15:04 UTC).")
    trace = [{"node": n, "status": "ok", "ms": 0} for n in ("identity", "route", "status", "respond")]
    return turn(reply=reply, language="pt", decision=None, case_id=case.case_id, trace=trace)


def two_turns(store: MemoryStore, session, text: str) -> dict:
    return block_and_open(store, session, text) if "débito" in text else status_turn(store, session, text)


def test_ac_10_a_status_turn_fills_one_status_reply_per_line_with_the_fresh_read():
    s = stack(two_turns)
    messages = [{"role": "customer", "text": t} for t in ("Não reconheço um débito", "Como está meu caso?")]
    [record] = run_set([{**case(), "messages": messages}], ["S0"], runs=1, api=Api(s.client))
    final = FinalState.model_validate(record["final_state"])
    assert [(r.subject[:2], r.stated_status, r.read_status) for r in final.status_replies] == [
        ("K-", "Em análise", "Em análise"), ("PR", "bloqueado", "bloqueado")]
    assert final.status_replies[1].subject == PRD


def test_ac_10_a_turn_that_is_not_a_status_answer_adds_no_status_reply():
    s = stack()
    [record] = run_set([case()], ["S0"], runs=1, api=Api(s.client))
    assert record["final_state"]["status_replies"] == []


# ---- AC-09: a turn the graph did not finish is a failed run, with the reason -------------------------------------
def test_ac_09_a_platform_failure_makes_a_failed_run_that_says_why():
    s = stack(lambda store, session, text: PlatformError("platform run error"))
    [record] = run_set([case()], ["S0"], runs=1, api=Api(s.client))
    assert record["status"] == "failed" and record["final_state"] is None
    assert "503" in record["error"] and "turn 1 ended without a graph turn" in record["error"]


def test_ac_09_the_harness_error_carries_the_apis_code_and_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"code": "INVALID", "policy_id": None, "message": "not in gold"})
    api = Api(httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(handler)))
    with pytest.raises(httpx.HTTPStatusError, match="422 POST /api/eval/seed - INVALID: not in gold"):
        api.run(case(), "EV-9001:S0:1", "S0")
