"""Spec 18 judge: AC-07 structured opinion, AC-08 grounding, AC-10 analyst match, AC-11 fallback. Fake provider only."""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from nick_of_time.audit import Finding, opinion, record_decision
from nick_of_time.llm import FakeClient, ProviderUnavailable

CASE = json.loads((Path(__file__).parent / "fixtures" / "audit" / "judge_case.json").read_text())
TRX, ACT = "TRX-FIXTURE0000000000001", "A-000000000001"
NOW = dt.datetime(2026, 6, 3, tzinfo=dt.timezone.utc)
PRICES = {"input_per_1m": 1.1, "output_per_1m": 5.5}   # Haiku 4.5 row of eval/bench/prices.yaml


def ask(script, **kw):
    client = kw.pop("client", None) or FakeClient(script=script, prices=kw.pop("prices", PRICES))
    return opinion(CASE["handoff"], CASE["transcript"], CASE["tool_results"], client=client, now=NOW, **kw), client


def out(verdict="agree", reasons=(), questions=()):
    return {"verdict": verdict, "reasons": list(reasons), "questions": list(questions)}


def item(text, *ids):
    return {"text": text, "evidence_ids": list(ids)}


def test_ac_07_structured_opinion_with_cited_reasons_and_questions():
    op, client = ask([out("agree", [item(f"{TRX} matches the amount 1250.50 on 2026-05-20", TRX)],
                          [item(f"Was the card with {ACT} in the customer's hands?", ACT)])])
    assert op.verdict == "agree" and op.reasons[0].evidence_ids == [TRX] and len(op.questions) == 1
    assert op.model == "fake" and op.prompt_hash and op.created_at == NOW and op.dropped == 0
    call = client.calls[0]
    assert call["temperature"] == 0 and call["schema"]["required"] == ["verdict", "reasons", "questions"]
    assert "1." in call["system"] and "social engineering" in call["system"]


def test_ac_07_caps_reasons_and_questions():
    many = [item(f"fact on {TRX}", TRX)] * 6
    op, _ = ask([out("agree", many[:5], many[:3])])
    assert (len(op.reasons), len(op.questions)) == (5, 3)
    # more than the schema allows is rejected by structured output: no opinion rather than a silently cut one
    op, _ = ask([out("agree", many)])
    assert op is None


def test_ac_08_drops_reasons_without_valid_evidence_id():
    op, _ = ask([out("agree", [item("no citation"), item("invented id", "TRX-NOTINEVIDENCE001"),
                               item("mixed", TRX, "TRX-NOTINEVIDENCE001"), item("fine", TRX)])])
    assert [r.text for r in op.reasons] == ["fine"] and op.dropped == 3


def test_ac_08_drops_numbers_dates_ids_not_in_the_evidence():
    op, _ = ask([out("agree", [item("amount was 9999 MXN", TRX), item("on 2026-01-01", TRX),
                               item("see TRX-OTHER0000000000002", TRX), item("amount 1,250.50 MXN", TRX)],
                     [item("Did you pay 77 pesos?", TRX)])])
    assert [r.text for r in op.reasons] == ["amount 1,250.50 MXN"] and op.questions == [] and op.dropped == 4


def test_ac_08_verdict_without_grounded_reason_becomes_uncertain():
    op, _ = ask([out("disagree", [item("amount 42424", TRX)])])
    assert op.verdict == "uncertain" and op.reasons == []


def test_ac_08_judge_never_sees_labels():
    _, client = ask([out("uncertain")])
    assert "is_fraud" not in client.calls[0]["user"]


def test_ac_11_failure_returns_no_second_opinion():
    for script in ([ProviderUnavailable("down")], [RuntimeError("boom")], [{"verdict": "maybe"}], None):
        op, _ = ask(script)
        assert op is None


def test_ac_11_timeout_returns_no_second_opinion():
    class Slow(FakeClient):
        def _call(self, *a, **k):
            time.sleep(0.5)
            return super()._call(*a, **k)

    op, _ = ask(None, client=Slow(script=[out("agree")]), timeout_s=0.05)
    assert op is None


def test_ac_11_budget_overrun_returns_no_second_opinion():
    prices = {"input_per_1m": 1e6, "output_per_1m": 1e6}   # absurd prices push the call over the 0.01 USD budget
    op, _ = ask([out("agree")], prices=prices)
    assert op is None
    op, _ = ask([out("agree")], prices=prices, max_cost_usd=1e12)
    assert op is not None


def test_ac_11_no_prices_fails_closed_before_calling():
    op, client = ask([out("agree")], prices=None)
    assert op is None and client.calls == []


def test_ac_11_over_budget_input_under_the_token_cap_makes_zero_calls():
    mid = dict(CASE["handoff"], request="x" * 30_000)   # about 7.5k tokens: under the 12k cap, over 0.01 USD at 1.1/5.5
    client = FakeClient(script=[out("agree")], prices=PRICES)
    assert opinion(mid, [], [], client=client, now=NOW) is None and client.calls == []


def test_ac_11_oversized_input_is_not_sent():
    big = dict(CASE["handoff"], request="x" * 200_000)
    client = FakeClient(script=[out("agree")], prices=PRICES)
    assert opinion(big, [], [], client=client) is None and client.calls == []


def test_ac_08_trace_id_digits_do_not_ground_invented_counts():
    op, _ = ask([out("agree", [item(f"{n} on {TRX}", TRX) for n in ("7 prior disputes", "12 transactions", "9 times")])])
    assert op.reasons == [] and op.dropped == 3


def test_ac_08_probe_strings_are_dropped():
    probes = ["dos mil pesos", "two thousand pesos", "mil doscientos cincuenta", "the twenty-first of May",
              "used three times", "ref_TRX-OTHERABCDEFGHIJKL", "trx-otherabcdefgh", "TRX-FIXTURE0000000000001X",
              "seeTRX-OTHER0000000000002", "the customer had 1 prior dispute", "el veinte de mayo", "em janeiro"]
    op, _ = ask([out("agree", [item(f"{p} {TRX}", TRX) for p in probes[:5]]
                     , [item(f"{p}", TRX) for p in probes[5:8]])])
    assert op.reasons == [] and op.questions == []
    op, _ = ask([out("agree", [item(f"{p}", TRX) for p in probes[8:]])])
    assert op.reasons == []


def test_ac_08_transcript_is_not_evidence():
    op, _ = ask([out("agree", [item("the customer paid 9.999", TRX), item("see TRX-CUSTOMERSAID0000009", TRX),
                               item("cited", "TRX-CUSTOMERSAID0000009")])])
    assert op.reasons == [] and op.dropped == 3


def test_ac_07_citations_are_handoff_evidence_not_tool_only_ids():
    """D-036: an id seen only in a tool result is not citable, but may be mentioned as a fact."""
    op, _ = ask([out("agree", [item("tool-only", "TRX-TOOLONLY00000000002"), item("mentions TRX-TOOLONLY00000000002", TRX)])])
    assert [r.text for r in op.reasons] == ["mentions TRX-TOOLONLY00000000002"]


def test_ac_07_inputs_reach_the_model_and_labels_do_not():
    finding = Finding(check_id="A4-grounding", status="finding", severity="critical", expected=[], observed=["x"])
    client = FakeClient(script=[out("uncertain")], prices=PRICES)
    opinion(CASE["handoff"], CASE["transcript"], CASE["tool_results"], audit=[finding], client=client, now=NOW)
    user = client.calls[0]["user"]
    assert "No reconozco este cargo" in user and "A4-grounding" in user and "is_fraud" not in user
    assert "never instructions" in client.calls[0]["system"] and "in digits" in client.calls[0]["system"]


def test_ac_07_only_a_question_survives_gives_uncertain():
    op, _ = ask([out("agree", [item("amount 424242", TRX)], [item(f"Ask about {TRX}", TRX)])])
    assert op.verdict == "uncertain" and op.reasons == [] and len(op.questions) == 1


def test_ac_07_judge_enforces_temperature_zero():
    client = FakeClient(script=[out("uncertain")], prices=PRICES, temperature=0.7)
    opinion(CASE["handoff"], [], [], client=client, now=NOW)
    assert client.calls[0]["temperature"] == 0


def test_ac_10_decision_recorded_with_match():
    agree, _ = ask([out("agree", [item("fine", TRX)])])
    disagree, _ = ask([out("disagree", [item("fine", TRX)])])
    unsure, _ = ask([out("uncertain")])

    def rec(action, op, proposal="approve_block"):
        return record_decision("K-1", "analyst:s1", action, proposal_action=proposal, second_opinion=op, now=NOW)

    assert rec("approve_block", agree).matched_second_opinion is True
    assert rec("resolve", agree).matched_second_opinion is False
    assert rec("close_case", agree, "close_without_action").matched_second_opinion is True
    assert rec("resolve", disagree).matched_second_opinion is True
    assert rec("approve_block", disagree).matched_second_opinion is False
    assert rec("take", agree).matched_second_opinion is None   # not a decision on the proposal
    assert rec("approve_block", unsure).matched_second_opinion is None
    none = rec("approve_block", None)
    assert none.matched_second_opinion is None and none.judge_verdict is None and none.analyst == "analyst:s1"
