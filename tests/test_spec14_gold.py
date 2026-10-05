"""Spec 14 T3–T4: gold `ops_kpis` and `feedback_cases`, the manifest and the ops_kpis.json export, on the seeded
in-memory store and the tiny gold fixture of tests/test_spec14_bronze_silver.py. Offline, no real gold."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl
import pytest

from data.ops import bronze, sample
from data.ops.run import run
from tests import test_spec14_bronze_silver as base
from tests.test_spec14_bronze_silver import CUSTOMERS, NOW, T0, read

gold, store = base.gold, base.store                          # the shared pytest fixtures

FIXTURE = Path(__file__).resolve().parents[1] / "apps/web/app/analytics/__fixtures__/ops_kpis.json"


def job(source, gold: Path, out: Path, **kw) -> dict:
    snap = source if isinstance(source, bronze.Snapshot) else bronze.from_memory(source)
    return run(snap, gold_path=gold, out=out, now=NOW, **kw)


def test_ac_03_ops_kpis_per_day_and_mode(store, gold, tmp_path):
    """AC-03: cases, receipt_rate, escalation, unsafe outcomes, cost and p95 per day, each rate with its counts."""
    job(store, gold, tmp_path)
    replay = read(tmp_path, "gold", "ops_kpis").filter(pl.col("mode") == "replay").row(0, named=True)
    assert replay["day"] == dt.date(2026, 6, 1) and replay["cases"] == 3
    assert (replay["receipt_rate_numerator"], replay["receipt_rate_denominator"]) == (1, 3)
    assert (replay["escalation_rate_numerator"], replay["escalation_rate_denominator"]) == (2, 3)
    assert replay["unsafe_outcomes"] == 0 and replay["denials"] == 1
    assert replay["cost_usd"] == pytest.approx(0.0126) and replay["cost_per_case"] == pytest.approx(0.0042)
    assert replay["latency_p95_ms"] == 2000                                  # nearest rank of 1500, 1750, 2000


def test_ac_03_a_lifecycle_breach_counts_as_unsafe(store, gold, tmp_path):
    """AC-03: a case resolved by the agent (audit A7, critical) is an unsafe outcome of its day."""
    snap = bronze.from_memory(store)
    case = next(c for c in snap.rows["cases"] if c["zone"] == "human" and c["run_id"] is None)
    seq = sum(e["case_id"] == case["case_id"] for e in snap.rows["case_events"]) + 1
    bad = {"event_id": "E-0000000000AA", "case_id": case["case_id"], "seq": seq, "type": "status_changed",
           "actor": "agent", "payload": {"to": "resolved"}, "customer_visible": True, "trace_id": "T-x",
           "created_at": T0.isoformat()}
    job(bronze.Snapshot.of("memory", {**snap.rows, "case_events": snap.rows["case_events"] + [bad]}), gold, tmp_path)
    assert read(tmp_path, "gold", "ops_kpis").filter(pl.col("mode") == "replay")["unsafe_outcomes"].to_list() == [1]


def test_ac_04_feedback_cases_hold_the_analyst_decision(store, gold, tmp_path):
    """AC-04: one row per case a person decided, with the system's intake action and whether the analyst kept it."""
    job(store, gold, tmp_path)
    rows = {r["zone"]: r for r in read(tmp_path, "gold", "feedback_cases").iter_rows(named=True)}
    assert set(rows) == {"high", "medium"}
    high, medium = rows["high"], rows["medium"]
    assert (high["agent_decision"], high["analyst_decision"], high["agreed"]) == ("block_and_open_case", "close_case",
                                                                               True)
    assert (medium["agent_decision"], medium["analyst_decision"], medium["agreed"]) == ("open_case", "approve_block",
                                                                                     False)
    assert high["analyst_reason"] == "customer informed" and high["segment"] == "Basic"


def test_ac_05_a_repeated_run_gives_the_same_gold_and_version(store, gold, tmp_path):
    """AC-05: same source rows → identical gold tables and hashes; the version moves only when a table changes."""
    first = job(store, gold, tmp_path)
    tables = {t: read(tmp_path, "gold", t) for t in first["tables"]}
    second = job(store, gold, tmp_path)
    assert second["version"] == first["version"] == 1 and second["changed_tables"] == []
    assert {t: m["sha256"] for t, m in second["tables"].items()} == {t: m["sha256"] for t, m in first["tables"].items()}
    for t, frame in tables.items():
        assert read(tmp_path, "gold", t).equals(frame)
    sample.seed(store, sample.gold_transactions(gold)[:1])
    third = job(store, gold, tmp_path)
    assert third["version"] == 2 and "ops_kpis" in third["changed_tables"]


def test_ac_07_eval_rows_and_synthetic_cases_stay_apart(store, gold, tmp_path):
    """AC-07: rows with a run_id never reach gold; the synthetic live case is only in a `live` row and is never a
    label; every gold row carries its mode."""
    manifest = job(store, gold, tmp_path)
    kpis, feedback = read(tmp_path, "gold", "ops_kpis"), read(tmp_path, "gold", "feedback_cases")
    assert sorted(kpis["mode"]) == ["live", "replay"] and kpis["mode"].null_count() == 0
    assert feedback["mode"].to_list() == ["replay"] * feedback.height
    assert kpis.filter(pl.col("mode") == "live")["cases"].to_list() == [1]
    assert manifest["source"]["eval_rows_excluded"]["cases"] == 1
    assert manifest["source"]["eval_rows_excluded"]["llm_calls"] == 1
    assert "TRX-SYNTHETIC000000000001" not in set(feedback["transaction_id"])


def test_ac_08_gold_holds_no_personal_data_label_score_or_transcript(store, gold, tmp_path):
    """AC-08: no gold column or value is a customer id, a name, the fraud label, the bank's score or a text."""
    job(store, gold, tmp_path)
    forbidden = {"customer_id", "first_name", "last_name", "document_number", "email", "phone", "address",
                 "is_fraud", "fraud_score", "text", "payload", "masked_address", "detail", "transcript"}
    for table in ("ops_kpis", "feedback_cases"):
        frame = read(tmp_path, "gold", table)
        assert not forbidden & set(frame.columns)
        assert not any(value in frame.write_csv() for value in [*CUSTOMERS, "Ana", "77.0"])


def test_ac_09_export_has_the_envelope_and_the_shape_of_7_4(store, gold, tmp_path):
    """AC-09: ops_kpis.json is {generated_at, git_sha, source, data}, every figure labeled [simulated]; the web
    fixture has the same shape."""
    job(store, gold, tmp_path, web=tmp_path / "ops_kpis.json")
    payload = json.loads((tmp_path / "ops_kpis.json").read_text())
    assert set(payload) == {"generated_at", "git_sha", "source", "data"} and "[simulated]" in payload["source"]
    data = payload["data"]
    assert (data["label"], data["mode"], data["feedback"]) == ("[simulated]", "replay", {"decided": 2, "agreed": 1})
    assert data["days"][0]["receipt_rate"] == {"value": pytest.approx(1 / 3), "numerator": 1, "denominator": 3}

    def shape(node):
        if isinstance(node, dict):
            return {k: shape(v) for k, v in node.items()}
        return [shape(node[0])] if isinstance(node, list) and node else type(node).__name__

    fixture = json.loads(FIXTURE.read_text())
    assert shape(fixture) == shape(payload)


def test_ac_11_quarantine_counts_reach_the_manifest(store, gold, tmp_path):
    """AC-11: the quality counts of silver are recorded in the manifest's checks."""
    snap = bronze.from_memory(store)
    bad = {**snap.rows["llm_calls"][0], "call_id": "LC-0000000000B4", "latency_ms": -5}
    manifest = job(bronze.Snapshot.of("memory", {**snap.rows, "llm_calls": snap.rows["llm_calls"] + [bad]}), gold,
                   tmp_path)
    checks = {(c["table"], c["id"]): c["n"] for c in manifest["checks"]}
    assert checks[("llm_calls", "quarantined")] == 1
    assert checks[("llm_calls", "latency_ms:greater_than_or_equal_to")] == 1
