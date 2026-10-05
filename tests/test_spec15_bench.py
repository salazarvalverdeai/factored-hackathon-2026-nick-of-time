"""Spec 15 (model benchmark): arms, prices, budget guard, smoke test and gate. Fake provider or stubbed boto3 client
only, no network."""
from __future__ import annotations

import re

import boto3
import pytest
from botocore.exceptions import ClientError, ConnectionClosedError, ParamValidationError, ReadTimeoutError

from eval.bench import core, gate, smoke

ARMS = core.load_arms()
PRICES = core.load_prices()
LLM = [a for a in ARMS if a["llm"]]
BILLABLE = [a for a in ARMS if core.is_billable(a)]
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KW = dict(n_messages=1000, in_tokens=500, out_tokens=100)


def test_arms_and_prices_cover_each_other():
    """AC-05: every billable arm has a price with source and date; the arms of section 4.1 are present."""
    ids = {a["id"] for a in ARMS}
    assert {"b0_rules", "b1_tfidf_lr", "jev", "haiku-4-5", "sonnet-5-5", "sonnet-4-6"} <= ids
    for a in BILLABLE:
        p = PRICES[a["id"]]
        assert p["source_url"] and ISO.match(str(p["checked_on"]))
        assert p["status"] in ("confirmed", "assumption")
        assert p["label"] == ("[external]" if p["status"] == "confirmed" else "[assumption]")
    assert {i for i, p in PRICES.items() if p["status"] == "assumption"} == {"jev"}
    for a in LLM:  # lifecycle from each model card; Legacy arms may come back unavailable (AC-06)
        assert a["lifecycle"]["model_card"].startswith("https://docs.aws.amazon.com/bedrock/latest/userguide/")
    assert {a["id"] for a in LLM if a["lifecycle"]["state"] == "legacy"} == {
        "gemma-3-12b", "gemma-3-27b", "llama-3-3-70b", "llama-4-scout", "llama-4-maverick"}


def test_ac_05_prices_match_the_price_list():
    """AC-05: Nova Micro and Lite use the on-demand Ohio figures of spec 4.1, not another tier's."""
    assert (PRICES["nova-micro"]["input_per_1m"], PRICES["nova-micro"]["output_per_1m"]) == (0.035, 0.14)
    assert (PRICES["nova-lite"]["input_per_1m"], PRICES["nova-lite"]["output_per_1m"]) == (0.06, 0.24)


def test_ac_05_row_stores_provenance():
    row = core.make_row(LLM[0], PRICES, "prompt text", "2026-10-04")
    for k in ("model_id", "version", "prompt_hash", "price_input_per_1m", "price_output_per_1m",
              "price_source_url", "price_checked_on", "run_date"):
        assert row[k] is not None
    assert row["prompt_hash"] == core.prompt_hash("prompt text") != core.prompt_hash("other")


def test_ac_08_budget_guard_refuses_over_budget():
    cost = core.projected_spend(ARMS, PRICES, **KW)
    assert 0 < cost < core.BUDGET_USD
    core.check_budget(cost)
    huge = core.projected_spend(ARMS, PRICES, 10_000_000, 500, 100)
    with pytest.raises(core.BudgetExceeded, match="no model was called"):
        core.check_budget(huge)


def test_ac_08_billable_arm_without_price_raises():
    """AC-08: the paid Jev arm counts as billable (it is not an LLM arm), and no price means no run."""
    jev = next(a for a in ARMS if a["id"] == "jev")
    assert core.is_billable(jev) and not jev["llm"]
    with pytest.raises(KeyError):
        core.projected_spend([jev], {}, 1, 1, 1)
    assert core.projected_spend([jev], PRICES, 1000, 500, 100) > 0


def test_ac_08_run_arms_refuses_before_any_call():
    calls = []
    with pytest.raises(core.BudgetExceeded):
        core.run_arms(ARMS, PRICES, "p", "2026-10-04", lambda a: calls.append(a) or {},
                      n_messages=10_000_000, in_tokens=500, out_tokens=100)
    assert calls == []


def test_ac_08_smoke_entry_point_refuses_before_any_call():
    calls = []
    pricey = {a["id"]: {"input_per_1m": 1e9, "output_per_1m": 1e9} for a in LLM}
    with pytest.raises(core.BudgetExceeded):
        smoke.run_smoke(ARMS, lambda *a: calls.append(a), pricey)
    assert calls == []


def test_ac_06_unavailable_arm_is_recorded_and_run_continues():
    def evaluate(arm):
        if arm["id"] == "sonnet-5-5":
            raise core.ProviderUnavailable("AccessDeniedException: not available for this account")
        return {"macro_f1": 0.5}
    rows = core.run_arms(ARMS, PRICES, "p", "2026-10-04", evaluate, **KW)
    assert len(rows) == len(ARMS)  # nothing silently dropped
    by = {r["arm"]: r for r in rows}
    assert by["sonnet-5-5"]["status"] == "unavailable" and "AccessDenied" in by["sonnet-5-5"]["reason"]
    assert by["sonnet-4-6"]["status"] == "ok"  # the arm after the failing one still ran


def test_ac_06_harness_bug_is_not_recorded_as_unavailable():
    def evaluate(arm):
        raise ZeroDivisionError("bug")
    with pytest.raises(ZeroDivisionError):
        core.run_arms(ARMS, PRICES, "p", "2026-10-04", evaluate, **KW)


def client_error(code, message):
    return ClientError({"Error": {"Code": code, "Message": message}}, "Converse")


@pytest.mark.parametrize("exc, unavailable", [
    (client_error("AccessDeniedException", "not available for this account"), "AccessDeniedException"),
    (client_error("ValidationException", "The provided model identifier is invalid."), "config:"),
    (client_error("ValidationException", "Invocation of model ID x with on-demand throughput isn't supported. "
                  "Retry your request with the ID or ARN of an inference profile."), "config:"),
    (client_error("ValidationException", "The value at maxTokens exceeds the model limit"), None),
    (ParamValidationError(report="Unknown parameter in toolConfig: \"toolChoise\""), None),
])
def test_ac_06_only_provider_errors_make_an_arm_unavailable(exc, unavailable):
    """AC-06: access, quota and a wrong model id (config) are unavailable; our malformed or invalid request
    (ParamValidationError, any other ValidationException) is a harness bug and propagates."""
    def evaluate(arm):
        raise exc
    if unavailable is None:
        with pytest.raises(type(exc)):
            core.run_arms(ARMS, PRICES, "p", "2026-10-04", evaluate, **KW)
    else:
        rows = core.run_arms(ARMS, PRICES, "p", "2026-10-04", evaluate, **KW)
        assert all(r["status"] == "unavailable" and unavailable in r["reason"] for r in rows)


def fake_provider(model_id, system, user, schema, mode):
    ok = {"tool_input": {"intent": "unrecognized_charge", "language": "es"}, "text": "", "stop_reason": "tool_use"}
    if "nova-micro" in model_id:
        return {"tool_input": None, "text": "Claro! Es una disputa.", "stop_reason": "end_turn"}
    if "nova-lite" in model_id:
        return {"tool_input": {"intent": "dispute"}, "text": "", "stop_reason": "tool_use"}  # language missing
    if "sonnet-5-5" in model_id:
        raise core.ProviderUnavailable("AccessDeniedException")
    return ok


def test_ac_11_smoke_test_classifies_each_llm_arm():
    res = smoke.run_smoke(ARMS, fake_provider)
    assert set(res) == {a["id"] for a in LLM}  # B0, B1 and Jev are not LLM arms
    assert res["nova-micro"]["result"] == "no structured output" and "end_turn" in res["nova-micro"]["reason"]
    assert res["nova-lite"]["result"] == "no structured output"
    assert res["sonnet-5-5"]["result"] == "unavailable" and "AccessDenied" in res["sonnet-5-5"]["reason"]
    assert res["haiku-4-5"]["result"] == "pass" and res["haiku-4-5"]["tool_choice_mode"] == "tool"
    assert "nova-micro" not in smoke.eligible(res) and "haiku-4-5" in smoke.eligible(res)


TOOL_REPLY = {"output": {"message": {"content": [{"toolUse": {"toolUseId": "t1", "name": smoke.TOOL_NAME,
                                                               "input": {"intent": "dispute", "language": "es"}}}]}},
              "stopReason": "tool_use"}


def stub_bedrock(monkeypatch, reply):
    """Stub boto3.client: `reply(request)` returns a Converse response or raises; the requests are captured."""
    sent = []

    class Client:
        def converse(self, **request):
            sent.append(request)
            return reply(request)
    monkeypatch.setattr(boto3, "client", lambda *a, **k: Client())
    return smoke.bedrock_provider(), sent


def test_ac_11_bedrock_request_forces_the_tool_with_the_schema_and_enough_tokens(monkeypatch):
    provider, sent = stub_bedrock(monkeypatch, lambda request: TOOL_REPLY)
    res = smoke.smoke_arm("us.anthropic.claude-haiku-4-5-20251001-v1:0", provider)
    assert res["result"] == "pass" and res["tool_choice_mode"] == "tool" and len(sent) == 1
    assert sent[0]["toolConfig"]["toolChoice"] == {"tool": {"name": smoke.TOOL_NAME}}
    assert sent[0]["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"] == {"json": smoke.INTENT_SCHEMA}
    assert sent[0]["inferenceConfig"]["maxTokens"] >= 512


def test_ac_11_temperature_zero_only_where_accepted_d016(monkeypatch):
    """AC-11 / D-016 (spec 15 section 4.1): temperature 0 is sent; a model that rejects it is retried once with the
    provider default and the setting is recorded per arm."""
    def reply(request):
        if "temperature" in request["inferenceConfig"] and "opus" in request["modelId"]:
            raise client_error("ValidationException", "temperature is not supported for this model")
        return TOOL_REPLY
    provider, sent = stub_bedrock(monkeypatch, reply)
    ok = smoke.smoke_arm("us.anthropic.claude-haiku-4-5-20251001-v1:0", provider)
    assert ok["result"] == "pass" and ok["temperature"] == 0
    assert sent[0]["inferenceConfig"]["temperature"] == 0
    res = smoke.smoke_arm("us.anthropic.claude-opus-x", provider)
    assert res["result"] == "pass" and res["temperature"] is None
    assert "temperature" in sent[1]["inferenceConfig"] and "temperature" not in sent[2]["inferenceConfig"]
    assert len(sent) == 3  # one retry, no ladder step


def test_ac_11_temperature_cache_is_per_model_and_budget_counts_the_retry(monkeypatch):
    """AC-11 / D-016: once a model rejected temperature it keeps getting the default, and others keep 0."""
    def reply(request):
        if "temperature" in request["inferenceConfig"] and "opus" in request["modelId"]:
            raise client_error("ValidationException", "temperature is not supported for this model")
        return TOOL_REPLY
    provider, sent = stub_bedrock(monkeypatch, reply)
    smoke.smoke_arm("us.anthropic.claude-opus-x", provider)
    n = len(sent)
    assert smoke.smoke_arm("us.anthropic.claude-haiku-4-5-20251001-v1:0", provider)["temperature"] == 0
    assert len(sent) == n + 1 and sent[-1]["inferenceConfig"]["temperature"] == 0
    assert smoke.smoke_arm("us.anthropic.claude-opus-x", provider)["temperature"] is None
    assert len(sent) == n + 2 and "temperature" not in sent[-1]["inferenceConfig"]
    seen = []
    monkeypatch.setattr(smoke, "projected_spend", lambda arms, prices, calls, i, o: seen.append(calls) or 0.0)
    smoke.run_smoke(ARMS, fake_provider)
    assert seen == [len(smoke.LADDER) + 1]


@pytest.mark.parametrize("exc", [
    client_error("ThrottlingException", "Too many requests"),
    client_error("AccessDeniedException", "no access"),
    ReadTimeoutError(endpoint_url="https://bedrock-runtime"),
    ConnectionClosedError(endpoint_url="https://bedrock-runtime"),
])
def test_ac_06_provider_errors_stay_unavailable_with_one_call(monkeypatch, exc):
    """AC-06 / AC-11: errors without a temperature complaint (even without a response) are not retried."""
    def reply(request):
        raise exc
    provider, sent = stub_bedrock(monkeypatch, reply)
    res = smoke.smoke_arm("us.amazon.nova-micro-v1:0", provider)
    assert res["result"] == "unavailable" and len(sent) == 1


def test_ac_11_rejected_tool_choice_steps_down_the_ladder(monkeypatch):
    """AC-11: toolChoice `tool` is documented for Claude and Nova only; an arm that rejects it is retried with `any`
    and records the mode B1 reuses, instead of being dropped by a request parameter."""
    def reply(request):
        if "tool" in request["toolConfig"]["toolChoice"]:
            raise client_error("ValidationException", "This model doesn't support the toolConfig.toolChoice.tool "
                                                      "field. Remove toolConfig.toolChoice.tool and try again.")
        return TOOL_REPLY
    provider, sent = stub_bedrock(monkeypatch, reply)
    res = smoke.smoke_arm("openai.gpt-oss-20b-1:0", provider)
    assert res["result"] == "pass" and res["tool_choice_mode"] == "any"
    assert [list(r["toolConfig"]["toolChoice"]) for r in sent] == [["tool"], ["any"]]


@pytest.mark.parametrize("message, result", [
    ("This model doesn't support tool use.", "no structured output"),  # after the whole ladder
    ("The provided model identifier is invalid.", "unavailable"),
])
def test_ac_11_validation_errors_are_classified(monkeypatch, message, result):
    def reply(request):
        raise client_error("ValidationException", message)
    provider, sent = stub_bedrock(monkeypatch, reply)
    res = smoke.smoke_arm("google.gemma-3-12b-it", provider)
    assert res["result"] == result and res["tool_choice_mode"] is None
    assert len(sent) == (3 if result == "no structured output" else 1)
    assert result != "unavailable" or res["reason"].startswith("config:")


@pytest.mark.parametrize("exc", [
    client_error("ValidationException", "The value at toolConfig.tools.0.toolSpec.inputSchema.json is invalid"),
    ParamValidationError(report="Invalid type for parameter inferenceConfig.maxTokens"),
])
def test_ac_11_our_request_errors_propagate(monkeypatch, exc):
    """AC-11: an invalid or malformed request is our bug, never "no structured output" or "unavailable"."""
    def reply(request):
        raise exc
    provider, _ = stub_bedrock(monkeypatch, reply)
    with pytest.raises(type(exc)):
        smoke.smoke_arm("us.amazon.nova-micro-v1:0", provider)


def test_ac_10_gate_has_both_verdicts_per_arm_and_criterion():
    rows = gate.gate_rows(ARMS, gate.load_evidence())
    arms = {r["arm"] for r in rows}
    assert "b0_rules" not in arms and "haiku-4-5" in arms and "jev" in arms
    assert {r["criterion"] for r in rows if r["arm"] == "haiku-4-5"} == set(gate.CRITERIA)
    assert all(r["verdict"] in ("pass", "fail", "not documented") for r in rows)
    # no verdict before the run: ES/PT quality is never pre-filled, and it is production-only (D-012)
    assert all(r["verdict"] == "not documented" and not r["needed_benchmark"]
               for r in rows if r["criterion"] == "es_pt_quality")
    sonnet = [r for r in rows if r["arm"] == "sonnet-5-5" and r["criterion"] == "availability"][0]
    assert sonnet["verdict"] == "fail" and sonnet["evidence_url"] and ISO.match(sonnet["checked_on"])


def test_ac_10_fully_evidenced_arm_may_benchmark_but_not_yet_run_in_production():
    summ = gate.summary(gate.gate_rows(ARMS, gate.load_evidence()))
    assert summ["haiku-4-5"]["benchmark"] is True
    assert summ["haiku-4-5"]["production"] is False  # availability and es_pt_quality still open
    # Bedrock ids are fixed versions by its lifecycle policy, with or without a version suffix (the S2 ceiling too)
    assert summ["sonnet-4-6"]["benchmark"] is True and summ["ministral-3-8b"]["benchmark"] is True


def test_ac_10_version_pinning_comes_from_provider_evidence_and_the_id_only_as_fallback():
    rows = gate.gate_rows(ARMS, gate.load_evidence())
    pin = {r["arm"]: r for r in rows if r["criterion"] == "version_pinning"}
    assert pin["sonnet-4-6"]["verdict"] == "pass" and "model-lifecycle" in pin["sonnet-4-6"]["evidence_url"]
    fallback = {r["arm"]: r["verdict"] for r in gate.gate_rows(ARMS, {"providers": {}})
                if r["criterion"] == "version_pinning"}
    assert fallback["haiku-4-5"] == fallback["jev"] == "pass"  # version in the id
    assert fallback["sonnet-4-6"] == "not documented"  # an unversioned id is not evidence of a failure
    assert "fail" not in fallback.values()


def test_ac_10_every_row_has_url_and_iso_date(tmp_path):
    rows = gate.gate_rows(ARMS, gate.load_evidence())
    assert all(ISO.match(r["checked_on"]) for r in rows)  # "not documented" rows are stamped too
    for r in rows:
        if r["verdict"] != "not documented":
            assert r["evidence_url"]
    gate.write_csv(rows, tmp_path / "bench_gate.csv")
    assert (tmp_path / "bench_gate.csv").read_text().startswith("arm,criterion")
