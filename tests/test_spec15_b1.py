"""Spec 15 T2: the B1 runner over arms x sentences (AC-01, AC-06, AC-08, D-011, D-016, D-022). Fake provider or a
stubbed boto3 client only, no network (CLAUDE.md)."""
from __future__ import annotations

import boto3
import pytest

from eval.bench import b1, core, smoke

ROWS = [{"id": f"V{i}", "language": lang, "intent": intent, "text": text, "slots": {"amount": "45", "date": None}}
        for i, (lang, intent, text) in enumerate([
            ("es", "unrecognized_charge", "No reconozco un cargo de 45 dólares en mi tarjeta."),
            ("es", "human_request", "Quiero hablar con una persona."),
            ("pt", "unrecognized_charge", "Não reconheço uma cobrança de 45 reais no meu cartão."),
            ("pt", "status_inquiry", "Como está o meu caso?")])]
PRICES = core.load_prices()


def stub_bedrock(monkeypatch, tool_input):
    sent = []

    class Client:
        def converse(self, **request):
            sent.append(request)
            content = [{"toolUse": {"toolUseId": "t", "name": smoke.TOOL_NAME, "input": tool_input(request)}}]
            return {"output": {"message": {"content": content if tool_input(request) else [{"text": "hola"}]}},
                    "stopReason": "tool_use", "usage": {"inputTokens": 600, "outputTokens": 50}}
    monkeypatch.setattr(boto3, "client", lambda *a, **k: Client())
    return smoke.bedrock_provider(), sent


def reading(intent):
    return {"intent": intent, "confidence": 0.9, "dispute_detected": True,
            "slots": {"amount": "45", "currency": None, "date": None, "merchant": None}}


def test_ac_01_every_arm_runs_on_the_same_sentences_and_unavailable_arms_are_recorded(monkeypatch):
    """AC-01, AC-06: every arm of arms.yaml gets a row on the same items; an arm that cannot run says why."""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    rows = b1.run(core.load_arms(), ROWS, b1.fake_provider, PRICES, "2026-10-05")
    assert [r["arm"] for r in rows] == [a["id"] for a in core.load_arms()]
    for r in rows:
        assert r["status"] in ("ok", "unavailable") and (r["status"] == "ok" or r["reason"])
        if r["status"] == "ok" and r["arm"] != "jev":
            assert [i["id"] for i in r["items"]] == [x["id"] for x in ROWS]


def test_ac_01_llm_arms_send_exactly_the_smoke_request_d011(monkeypatch):
    """AC-01 with D-011/D-016: the smoke call and every B1 call are `smoke.converse_request` with the understand prompt
    and schema; the accepted mode and temperature are recorded per arm, and per-row usage is priced."""
    provider, sent = stub_bedrock(monkeypatch, lambda req: reading("unrecognized_charge"))
    arm = next(a for a in core.load_arms() if a["id"] == "haiku-4-5")
    out = b1.llm_items(arm, ROWS, provider, PRICES["haiku-4-5"])
    assert len(sent) == 1 + len(ROWS)
    for request, text in zip(sent, [b1.SMOKE_TEXT] + [r["text"] for r in ROWS]):
        assert request == smoke.converse_request(arm["model_id"], b1.UNDERSTAND, b1.user_text(text), b1.INTENT_SCHEMA,
                                                 "tool", 0)
    assert out["tool_choice_mode"] == "tool" and out["temperature"] == 0
    assert out["items"][0]["cost_usd"] == pytest.approx((600 * 1.1 + 50 * 5.5) / 1e6)


def test_ac_01_missing_tool_call_scores_as_wrong_d022(monkeypatch):
    """D-022 (PROTOCOL §2.1): a reply without a tool call stays in the denominator as a wrong prediction."""
    provider, _ = stub_bedrock(monkeypatch, lambda req: None if "Como" in req["messages"][0]["content"][0]["text"]
                               else reading("unrecognized_charge"))
    arm = next(a for a in core.load_arms() if a["id"] == "nova-micro")
    items = b1.llm_items(arm, ROWS, provider, PRICES["nova-micro"])["items"]
    assert len(items) == len(ROWS) and [i["tool_call"] for i in items] == [True, True, True, False]
    assert [i["pred"] == i["gold"] for i in items] == [True, False, True, False]


def test_ac_08_budget_guard_stops_before_any_call():
    calls = []
    with pytest.raises(core.BudgetExceeded):
        b1.run(core.load_arms(), ROWS, lambda *a: calls.append(a), PRICES, "2026-10-05", budget=0.001)
    assert calls == []
