"""Spec 15 T2: the B1 runner over arms x sentences (AC-01, AC-06, AC-08, D-011, D-016, D-022). Fake provider or a
stubbed boto3 client only, no network (CLAUDE.md)."""
from __future__ import annotations

import io
import json
import urllib.error

import boto3
import pytest
from botocore.exceptions import ClientError

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


def test_ac_01_the_bench_request_is_the_production_request_d011():
    """AC-01 with D-011: the B1 request equals what the production Bedrock client sends for the `understand` step,
    tool description included, so the bench measures the D-082 prompt that S1 runs."""
    from nick_of_time.llm.bedrock import BedrockClient
    from nick_of_time.llm.steps import MAX_TOKENS
    arm = next(a for a in core.load_arms() if a["id"] == "haiku-4-5")
    user = b1.user_text(b1.SMOKE_TEXT)
    production = BedrockClient(arm["model_id"], boto_client=object()).request(
        b1.UNDERSTAND, user, b1.INTENT_SCHEMA, smoke.TOOL_NAME, MAX_TOKENS, "tool", 0)
    assert smoke.converse_request(arm["model_id"], b1.UNDERSTAND, user, b1.INTENT_SCHEMA, "tool", 0) == production


def test_ac_01_d078_missing_slot_keys_are_null_not_a_schema_failure(monkeypatch):
    """D-078: a reply that leaves out slot keys is a tool call with those slots null; it is scored, not dropped."""
    provider, _ = stub_bedrock(monkeypatch, lambda req: {**reading("unrecognized_charge"), "slots": {"amount": "45"}})
    arm = next(a for a in core.load_arms() if a["id"] == "nova-micro")
    items = b1.llm_items(arm, ROWS, provider, PRICES["nova-micro"])["items"]
    assert all(i["tool_call"] for i in items)
    assert items[0]["pred_slots"] == {"amount": "45", "currency": None, "date": None, "merchant": None}


def test_ac_05_adr_0027_records_the_prompt_hash_the_bench_measures():
    """AC-05 with D-082: the prompt hash every row stores is the one ADR 0027 records for the validation iteration."""
    adr = (b1.ROOT / "docs/adr/0027-model-selection.md").read_text(encoding="utf-8")
    assert f"`{core.prompt_hash(b1.PROMPT)}`" in adr


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


# Per-sentence errors (review of #179): one failed sentence is a wrong prediction counted in `errors`, never the end
# of the arm or of the run, and every scored item is on disk as soon as it exists.

def text_of(request):
    return json.loads(request["messages"][0]["content"][0]["text"])["message"]


def failing_bedrock(monkeypatch, fail):
    """Bedrock stub: `fail(text)` returns an exception to raise for that message (None answers normally)."""
    class Client:
        def converse(self, **request):
            exc = fail(text_of(request))
            if exc is not None:
                raise exc
            content = [{"toolUse": {"toolUseId": "t", "name": smoke.TOOL_NAME, "input": reading("unrecognized_charge")}}]
            return {"output": {"message": {"content": content}}, "stopReason": "tool_use",
                    "usage": {"inputTokens": 600, "outputTokens": 50}}
    monkeypatch.setattr(boto3, "client", lambda *a, **k: Client())
    return smoke.bedrock_provider()


def client_error(code, message):
    return ClientError({"Error": {"Code": code, "Message": message}}, "Converse")


def arms(*ids):
    return [a for a in core.load_arms() if a["id"] in ids]


def test_ac_06_an_error_on_one_sentence_keeps_the_arm_scores_it_wrong_and_counts_it(monkeypatch):
    """AC-06 with D-022: throttling after the retries on one sentence (ProviderUnavailable) no longer makes the arm
    unavailable nor drops the items already paid for; that sentence is wrong, stays in the denominator, is counted."""
    provider = failing_bedrock(monkeypatch, lambda t: client_error("ThrottlingException", "Rate exceeded")
                               if t == ROWS[1]["text"] else None)
    [row] = b1.run(arms("haiku-4-5"), ROWS, provider, PRICES, "2026-10-05")
    assert row["status"] == "ok" and row["errors"] == {"ProviderUnavailable": 1}
    assert [i["id"] for i in row["items"]] == [r["id"] for r in ROWS]
    bad = row["items"][1]
    assert bad["pred"] is None and bad["pred"] != bad["gold"] and bad["tool_call"] is False
    assert bad["error"].startswith("ProviderUnavailable: ThrottlingException") and bad["cost_usd"] == 0
    assert all(i["error"] is None for i in row["items"] if i is not bad)


def test_ac_06_an_unmapped_error_mid_run_does_not_abort_the_run(monkeypatch):
    """AC-01, AC-06: errors `core.provider_error` does not map (a ValidationException such as a content filter) and a
    ToolChoiceUnsupported mid-run are scored wrong on their sentence; every arm still gets its row."""
    def fail(text):
        if text == ROWS[2]["text"]:
            return client_error("ValidationException", "The input was blocked by a content filter.")
        if text == ROWS[3]["text"]:
            return client_error("ValidationException", "This model doesn't support the toolChoice field.")
        return None
    provider = failing_bedrock(monkeypatch, fail)
    chosen = arms("haiku-4-5", "nova-micro", "b0_rules")
    rows = b1.run(chosen, ROWS, provider, PRICES, "2026-10-05")
    assert [r["arm"] for r in rows] == [a["id"] for a in chosen]
    for r in (r for r in rows if r["arm"] != "b0_rules"):
        assert r["status"] == "ok" and len(r["items"]) == len(ROWS)
        assert r["errors"] == {"ClientError": 1, "ToolChoiceUnsupported": 1}
        assert [i["pred"] is None for i in r["items"]] == [False, False, True, True]


def test_ac_06_an_unmapped_error_at_the_smoke_step_makes_only_that_arm_unavailable(monkeypatch):
    """AC-06, AC-11: an arm that cannot start (its smoke call raises an error that maps to nothing) is recorded
    unavailable with the reason; the other arms run."""
    provider = failing_bedrock(monkeypatch, lambda t: client_error("ValidationException", "Malformed input request")
                               if t == b1.SMOKE_TEXT else None)
    rows = {r["arm"]: r for r in b1.run(arms("haiku-4-5", "b0_rules"), ROWS, provider, PRICES, "2026-10-05")}
    assert rows["haiku-4-5"]["status"] == "unavailable" and "smoke ClientError" in rows["haiku-4-5"]["reason"]
    assert rows["b0_rules"]["status"] == "ok" and len(rows["b0_rules"]["items"]) == len(ROWS)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def stub_jev(monkeypatch, answer):
    """urlopen stub: `answer(state)` returns the JSON body text for that message or raises."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    def urlopen(req, timeout):
        return FakeResponse(answer(json.loads(req.data)["state"]).encode())
    monkeypatch.setattr(b1.urllib.request, "urlopen", urlopen)


def jev_ok(intent):
    return json.dumps({"answers": {"intent": {"choice": intent}}, "usage": {"input_tokens": 300}})


def test_ac_06_jev_errors_on_sentences_are_scored_wrong_and_counted(monkeypatch):
    """AC-06 with D-022 for Jev: a URLError and an unreadable body (JSONDecodeError) on two sentences keep the arm."""
    def answer(state):
        if state == ROWS[1]["text"]:
            raise urllib.error.URLError("connection reset")
        return "<html>bad gateway</html>" if state == ROWS[3]["text"] else jev_ok("human_request")
    stub_jev(monkeypatch, answer)
    [row] = b1.run(arms("jev"), ROWS, b1.fake_provider, PRICES, "2026-10-05")
    assert row["status"] == "ok" and row["errors"] == {"URLError": 1, "JSONDecodeError": 1}
    assert [i["pred"] for i in row["items"]] == ["human_request", None, "human_request", None]
    assert row["smoke_cost_usd"] == pytest.approx(300 * PRICES["jev"]["input_per_1m"] / 1e6)


def test_ac_06_jev_unavailable_only_when_its_smoke_call_fails(monkeypatch):
    """AC-06: Jev is unavailable when it cannot start (the smoke call fails before any scored item)."""
    def answer(state):
        raise urllib.error.URLError("name or service not known")
    stub_jev(monkeypatch, answer)
    [row] = b1.run(arms("jev"), ROWS, b1.fake_provider, PRICES, "2026-10-05")
    assert row["status"] == "unavailable" and "jev smoke URLError" in row["reason"]


def test_ac_01_items_are_written_as_they_arrive(tmp_path):
    """AC-01, AC-05: with `items_path`, every scored item of every arm is appended to the JSONL with its arm."""
    path = tmp_path / "items.jsonl"
    rows = b1.run(arms("haiku-4-5", "b0_rules"), ROWS, b1.fake_provider, PRICES, "2026-10-05", items_path=path)
    on_disk = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert sorted((d["arm"], d["id"]) for d in on_disk) == sorted((r["arm"], i["id"]) for r in rows
                                                                  for i in r["items"])
    assert len(on_disk) == 2 * len(ROWS)


class Crash(BaseException):
    """Stands for the process dying mid-run (not an Exception, so nothing in the runner catches it)."""


def test_ac_06_items_paid_for_are_on_disk_after_a_mid_run_crash(tmp_path):
    """AC-06 (review of #179): a crash on the third sentence leaves the two items already scored on disk."""
    path = tmp_path / "items.jsonl"

    def provider(model_id, system, user, schema, mode):
        if json.loads(user)["message"] == ROWS[2]["text"]:
            raise Crash()
        return b1.fake_provider(model_id, system, user, schema, mode)
    with pytest.raises(Crash):
        b1.run(arms("haiku-4-5"), ROWS, provider, PRICES, "2026-10-05", items_path=path)
    on_disk = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert [(d["arm"], d["id"]) for d in on_disk] == [("haiku-4-5", "V0"), ("haiku-4-5", "V1")]
