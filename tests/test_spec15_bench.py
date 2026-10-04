"""Spec 15 (model benchmark): arms, prices, budget guard, smoke test and gate. Fake provider only, no network."""
from __future__ import annotations

import pytest

from eval.bench import core, gate, smoke

ARMS = core.load_arms()
PRICES = core.load_prices()
LLM = [a for a in ARMS if a["llm"]]


def test_arms_and_prices_cover_each_other():
    """AC-05: every LLM arm has a price with source and date; the lists of section 4.1 are present."""
    ids = {a["id"] for a in ARMS}
    assert {"b0_rules", "b1_tfidf_lr", "jev", "haiku-4-5", "sonnet-5-5", "sonnet-4-6"} <= ids
    for a in LLM + [a for a in ARMS if a["id"] == "jev"]:
        p = PRICES[a["id"]]
        assert p["source_url"] and p["checked_on"] == "2026-10-04"
        assert p["status"] in ("confirmed", "assumption")
        assert p["label"] == ("[external]" if p["status"] == "confirmed" else "[assumption]")


def test_ac_05_row_stores_provenance():
    row = core.make_row(LLM[0], PRICES, "prompt text", "2026-10-04")
    for k in ("model_id", "version", "prompt_hash", "price_input_per_1m", "price_output_per_1m",
              "price_source_url", "price_checked_on", "run_date"):
        assert row[k] is not None
    assert row["prompt_hash"] == core.prompt_hash("prompt text") != core.prompt_hash("other")


def test_ac_08_budget_guard_refuses_over_budget():
    cost = core.projected_spend(ARMS, PRICES, n_messages=1000, in_tokens=500, out_tokens=100)
    assert 0 < cost < core.BUDGET_USD
    core.check_budget(cost)
    huge = core.projected_spend(ARMS, PRICES, n_messages=10_000_000, in_tokens=500, out_tokens=100)
    with pytest.raises(core.BudgetExceeded, match="no model was called"):
        core.check_budget(huge)


def test_ac_08_llm_arm_without_price_is_refused():
    with pytest.raises(KeyError):
        core.projected_spend(LLM, {}, 1, 1, 1)


def test_ac_06_unavailable_arm_is_recorded_and_run_continues():
    def evaluate(arm):
        if arm["id"] == "sonnet-5-5":
            raise PermissionError("AccessDeniedException: not available for this account")
        return {"macro_f1": 0.5}
    rows = core.run_arms(ARMS, PRICES, "p", "2026-10-04", evaluate)
    assert len(rows) == len(ARMS)  # nothing silently dropped
    by = {r["arm"]: r for r in rows}
    assert by["sonnet-5-5"]["status"] == "unavailable" and "AccessDenied" in by["sonnet-5-5"]["reason"]
    assert by["haiku-4-5"]["status"] == "ok"


def fake_provider(model_id, system, user):
    if "nova-micro" in model_id:
        return "Claro! Es una disputa."  # no JSON
    if "nova-lite" in model_id:
        return '{"intent": "dispute"}'  # schema violation (language missing)
    if "sonnet-5-5" in model_id:
        raise RuntimeError("AccessDeniedException")
    if "haiku" in model_id:
        return '```json\n{"intent": "unrecognized_charge", "language": "es"}\n```'
    return '{"intent": "unrecognized_charge", "language": "es"}'


def test_ac_11_smoke_test_classifies_each_llm_arm():
    res = smoke.smoke_test(ARMS, fake_provider)
    assert set(res) == {a["id"] for a in LLM}  # B0, B1 and Jev are not LLM arms
    assert res["nova-micro"]["result"] == "no structured output"
    assert res["nova-lite"]["result"] == "no structured output"
    assert res["sonnet-5-5"]["result"] == "unavailable" and "AccessDenied" in res["sonnet-5-5"]["reason"]
    assert res["haiku-4-5"]["result"] == "pass"
    assert "nova-micro" not in smoke.eligible(res) and "haiku-4-5" in smoke.eligible(res)


def test_ac_10_gate_has_both_verdicts_per_arm_and_criterion():
    rows = gate.gate_rows(ARMS, gate.load_evidence())
    arms = {r["arm"] for r in rows}
    assert "b0_rules" not in arms and "haiku-4-5" in arms and "jev" in arms
    assert {r["criterion"] for r in rows if r["arm"] == "haiku-4-5"} == set(gate.CRITERIA)
    assert all(r["verdict"] in ("pass", "fail", "not documented") for r in rows)
    # no verdict before the run: ES/PT quality is never pre-filled
    assert all(r["verdict"] == "not documented" for r in rows if r["criterion"] == "es_pt_quality")
    summ = gate.summary(rows)
    assert summ["haiku-4-5"] == {"benchmark": False, "production": False}  # es_pt_quality still open
    sonnet = [r for r in rows if r["arm"] == "sonnet-5-5" and r["criterion"] == "availability"][0]
    assert sonnet["verdict"] == "fail" and sonnet["evidence_url"] and sonnet["checked_on"] == "2026-10-04"


def test_ac_10_pass_evidence_carries_url_and_date(tmp_path):
    rows = gate.gate_rows(ARMS, gate.load_evidence())
    for r in rows:
        if r["verdict"] != "not documented":
            assert r["evidence_url"] and r["checked_on"]
    gate.write_csv(rows, tmp_path / "bench_gate.csv")
    assert (tmp_path / "bench_gate.csv").read_text().startswith("arm,criterion")
