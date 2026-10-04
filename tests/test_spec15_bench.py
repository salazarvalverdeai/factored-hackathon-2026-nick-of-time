"""Spec 15 (model benchmark): arms, prices, budget guard, smoke test and gate. Fake provider only, no network."""
from __future__ import annotations

import re

import pytest

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


def fake_provider(model_id, system, user, schema):
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
    assert res["haiku-4-5"]["result"] == "pass"
    assert "nova-micro" not in smoke.eligible(res) and "haiku-4-5" in smoke.eligible(res)


def test_ac_11_smoke_uses_forced_tool_use_and_enough_tokens():
    assert smoke.MAX_TOKENS >= 512 and smoke.TOOL_NAME == "record_intent"


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
    assert summ["ministral-3-8b"]["benchmark"] is False  # unversioned id fails version pinning


def test_ac_10_version_pinning_is_derived_from_the_model_id():
    assert gate.version_pinned("us.anthropic.claude-haiku-4-5-20251001-v1:0")
    assert gate.version_pinned("amazon.nova-micro-v1:0") and gate.version_pinned("jev-1.13.0")
    assert not gate.version_pinned("us.anthropic.claude-sonnet-5-5") and not gate.version_pinned(None)


def test_ac_10_every_row_has_url_and_iso_date(tmp_path):
    rows = gate.gate_rows(ARMS, gate.load_evidence())
    assert all(ISO.match(r["checked_on"]) for r in rows)  # "not documented" rows are stamped too
    for r in rows:
        if r["verdict"] != "not documented":
            assert r["evidence_url"]
    gate.write_csv(rows, tmp_path / "bench_gate.csv")
    assert (tmp_path / "bench_gate.csv").read_text().startswith("arm,criterion")
