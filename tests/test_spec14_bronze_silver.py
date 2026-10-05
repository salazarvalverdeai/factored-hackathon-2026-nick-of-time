"""Spec 14 T1–T2: bronze and silver of the ops job on a seeded in-memory store over a tiny gold fixture. Offline: no
Postgres, no network, no real gold; `is_fraud` and data/gold_eval are never read. The fixtures here also serve
tests/test_spec14_gold.py."""
from __future__ import annotations

import datetime as dt
import itertools
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from data.ops import bronze, sample, silver
from nick_of_time.store.memory import MemoryStore

T0 = dt.datetime(2026, 10, 5, 12, 0, tzinfo=dt.UTC)
NOW = T0 + dt.timedelta(hours=1)
CUSTOMERS = {"CLI-AAAAAAAAAAA1": "México", "CLI-AAAAAAAAAAA2": "Colombia", "CLI-AAAAAAAAAAA3": "Argentina"}


@pytest.fixture
def gold(tmp_path: Path) -> Path:
    """Three card transactions (with the bank's score, which the job must never read) and their customers."""
    root = tmp_path / "gold"
    root.mkdir()
    ids = list(CUSTOMERS)
    pl.DataFrame({"transaction_id": [f"TRX-{i:020d}" for i in range(1, 4)], "customer_id": ids,
                  "product_id": [f"PRD-{i:012d}" for i in range(1, 4)],
                  "product_type": ["Tarjeta Débito", "Tarjeta Crédito", "Tarjeta Débito"],
                  "amount": [120.0, 80.5, 9.9], "currency": ["MXN", "COP", "ARS"],
                  "transaction_date": [dt.datetime(2026, 5, 30, 10)] * 3, "fraud_score": [77.0, 40.0, 5.0]},
                 ).write_parquet(root / "transactions_enriched.parquet")
    pl.DataFrame({"customer_id": ids, "country": list(CUSTOMERS.values()), "segment": ["Basic", "Plus", "Premium"],
                  "first_name": ["Ana", "Bruno", "Carla"]}).write_parquet(root / "customers.parquet")
    return root


@pytest.fixture
def store(gold: Path) -> MemoryStore:
    """Replay cases in the high, medium and human zones, one eval case and one synthetic live case."""
    ticks = itertools.count()
    clock = MemoryStore(now=lambda: T0 + dt.timedelta(milliseconds=next(ticks)))
    return sample.seed(clock, sample.gold_transactions(gold))


def layers(source: Any, gold: Path, out: Path) -> dict[str, Any]:
    snap = source if isinstance(source, bronze.Snapshot) else bronze.from_memory(source)
    return {"bronze": bronze.build(snap, out / "bronze", NOW),
            "silver": silver.build(out / "bronze", out / "silver", gold, NOW)["stats"]}


def read(out: Path, layer: str, table: str) -> pl.DataFrame:
    return pl.read_parquet(out / layer / f"{table}.parquet")


def test_ac_01_bronze_holds_every_source_row_with_its_load_time(store, gold, tmp_path):
    """AC-01: each of the eight tables lands in bronze, schema.sql columns plus `_loaded_at` and `_source`, with the
    source's row count and high-water mark."""
    stats = layers(store, gold, tmp_path)["bronze"]
    snap = bronze.from_memory(store)
    for table in bronze.TABLES:
        frame = read(tmp_path, "bronze", table)
        assert frame.columns == bronze.COLUMNS[table] + ["_loaded_at", "_source"]
        assert frame.height == snap.counts[table] == stats[table]["rows"]
        assert set(frame["_source"]) <= {"memory"} and set(frame["_loaded_at"]) <= {NOW}
    assert stats["case_events"]["high_water"] == snap.high_water["case_events"].isoformat()
    assert snap.counts["cases"] == 5 and snap.counts["llm_calls"] == 5


def test_ac_01_a_lost_row_stops_the_run(store, gold, tmp_path):
    """AC-01: a bronze count that differs from the source's own count fails the run."""
    snap = bronze.from_memory(store)
    short = bronze.Snapshot("memory", {**snap.rows, "cases": snap.rows["cases"][1:]}, snap.counts, snap.high_water)
    with pytest.raises(RuntimeError, match="lost rows"):
        layers(short, gold, tmp_path)


def test_ac_02_silver_joins_gold_and_passes_the_contracts(store, gold, tmp_path):
    """AC-02: every event carries its case's context and the gold segment and amount; nothing is quarantined."""
    stats = layers(store, gold, tmp_path)["silver"]
    events = read(tmp_path, "silver", "case_events").filter(pl.col("mode") == "replay")
    assert events["segment"].null_count() == 0 and events["amount"].null_count() == 0
    assert {"status_to", "action", "reason", "zone", "country", "transaction_date"} <= set(events.columns)
    assert "payload" not in events.columns
    assert all(s["quarantined"] == 0 for s in stats.values())
    cases = read(tmp_path, "silver", "cases")
    replay_high = cases.filter(pl.col("zone") == "high", pl.col("run_id").is_null(), pl.col("mode") == "replay")
    assert replay_high["block_verified"].to_list() == [True] and replay_high["queue_status"].to_list() == ["closed"]
    assert cases["qc_gold_missing"].sum() == 0 and cases["synthetic"].sum() == 1


def test_ac_02_a_customer_missing_from_gold_raises_qc_gold_missing(store, gold, tmp_path):
    """AC-02: a gold row that is not found leaves the gold columns null and is flagged, not dropped."""
    pl.read_parquet(gold / "customers.parquet").head(1).write_parquet(gold / "customers.parquet")
    stats = layers(store, gold, tmp_path)["silver"]
    cases = read(tmp_path, "silver", "cases")
    assert stats["cases"]["qc_gold_missing"] == cases["segment"].null_count() > 0
    assert cases.height == stats["cases"]["rows_bronze"]


def test_ac_02_gold_eval_is_refused(tmp_path):
    """AC-02, constitution #7: the job reads data/gold only."""
    with pytest.raises(ValueError, match="gold_eval"):
        silver.read_gold(tmp_path / "gold_eval", [], [])


def test_ac_11_a_row_that_breaks_a_contract_is_quarantined_and_counted(store, gold, tmp_path):
    """AC-11: bad rows stay in bronze, go to quarantine with their reason, are counted, and the job finishes."""
    snap = bronze.from_memory(store)
    case_id = snap.rows["cases"][0]["case_id"]
    base = {"customer_visible": True, "trace_id": "T-x", "actor": "agent", "payload": {}, "created_at": T0.isoformat()}
    bad_events = [{**base, "event_id": "E-0000000000B1", "case_id": case_id, "seq": 99, "type": "receipt_issued"},
                  {**base, "event_id": "E-0000000000B2", "case_id": "K-999999", "seq": 1, "type": "case_opened"},
                  {**base, "event_id": "E-0000000000B3", "case_id": case_id, "seq": 100, "type": "bogus",
                   "created_at": (NOW + dt.timedelta(days=1)).isoformat()},
                  {**base, "event_id": "E-0000000000B5", "case_id": case_id, "seq": 101, "type": "receipt_issued",
                   "payload": "{not json"}]
    bad_call = {**snap.rows["llm_calls"][0], "call_id": "LC-0000000000B4", "latency_ms": -5}
    rows = {**snap.rows, "case_events": snap.rows["case_events"] + bad_events,
            "llm_calls": snap.rows["llm_calls"] + [bad_call]}
    stats = layers(bronze.Snapshot.of("memory", rows), gold, tmp_path)["silver"]
    assert read(tmp_path, "bronze", "case_events").height == len(rows["case_events"])
    quarantined = read(tmp_path, "silver/_quarantine", "case_events")
    reasons = dict(zip(quarantined["event_id"], quarantined["_quarantine_reason"]))
    assert "seq:continuous" in reasons["E-0000000000B1"]
    assert "case_id:case_exists" in reasons["E-0000000000B2"]
    assert {"type:isin", "created_at:less_than_or_equal_to"} <= set(reasons["E-0000000000B3"].split("; "))
    assert "payload:json_object" in reasons["E-0000000000B5"]
    assert not set(reasons) & set(read(tmp_path, "silver", "case_events")["event_id"])
    assert stats["case_events"]["quarantined"] == 4 and stats["llm_calls"]["quarantined"] == 1
    assert stats["case_events"]["contract_failures"]["seq:continuous"] == 3
    assert stats["llm_calls"]["contract_failures"] == {"latency_ms:greater_than_or_equal_to": 1}
