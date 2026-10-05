"""Spec 09 T1 — the demo index: queries/eval/demo_index.sql and the committed eval/demo_index.csv.

Offline: the query runs on a small gold fixture built in tmp_path; the committed CSV is checked as a file."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import pytest

from eval import demo_index
from nick_of_time.policy import PolicyEngine

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = ["customer_id", "country", "segment", "split", "product_id", "product_type", "transaction_id",
           "transaction_date", "amount", "currency", "merchant_name", "fraud_score", "zone", "amount_tier",
           "n_candidates_7d"]
QC = ["qc_customer_orphan", "qc_product_orphan", "qc_product_other_customer", "qc_before_product_open",
      "qc_future_date", "qc_late_arrival", "qc_label_normalized"]
TIER = {"auto": "low", "manual_check": "mid", "human_required": "above_high"}      # amount_gate.tiers
DEV, HELDOUT, TRAIN = "CLI-DEV-0", "CLI-HELD-2", "CLI-TRAIN-4"                      # buckets 7, 8 and 2
ROWS = demo_index.read()


def gold(tmp_path: Path, rows: list[dict]) -> Path:
    """A gold folder with only the columns the query reads; every row is a kept candidate unless it says otherwise."""
    base = {"customer_id": DEV, "product_id": "PRD-1", "transaction_date": datetime(2026, 5, 20, 10, 0),
            "amount": 100.0, "currency": "USD", "merchant_name": "TIENDA X", "transaction_status": "Approved",
            "fraud_score": 72.0, "product_type": "Tarjeta Crédito", "customer_country": "México",
            "customer_segment": "Basic", **dict.fromkeys(QC, False)}
    rows = [{**base, "transaction_id": f"TRX-{i:03d}", **row} for i, row in enumerate(rows)]
    folder = tmp_path / "data/gold"
    folder.mkdir(parents=True)
    con = duckdb.connect()
    con.execute("CREATE TABLE t (customer_id VARCHAR, product_id VARCHAR, transaction_id VARCHAR,"
                " transaction_date TIMESTAMP, amount DOUBLE, currency VARCHAR, merchant_name VARCHAR,"
                " transaction_status VARCHAR, fraud_score DOUBLE, product_type VARCHAR, customer_country VARCHAR,"
                " customer_segment VARCHAR, " + ", ".join(f"{flag} BOOLEAN" for flag in QC) + ")")
    names = list(rows[0])
    con.executemany(f"INSERT INTO t ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",
                    [[row[name] for name in names] for row in rows])
    con.execute(f"COPY t TO '{(folder / 'transactions_enriched.parquet').as_posix()}' (FORMAT parquet)")
    con.close()
    return tmp_path


def built(tmp_path: Path, rows: list[dict]) -> list[dict]:
    columns, out = demo_index.build(gold(tmp_path, rows))
    assert columns == COLUMNS
    return [dict(zip(columns, row)) for row in out]


def test_ac_01_keeps_only_approved_own_card_transactions_in_the_window(tmp_path):
    """AC-01: cards only, the customer's own, inside the window of §7.2, no qc flag raised."""
    out = built(tmp_path, [
        {"transaction_id": "TRX-KEEP"},
        {"transaction_id": "TRX-FIRST-DAY", "transaction_date": datetime(2026, 3, 3, 0, 0)},
        {"transaction_id": "TRX-LAST-DAY", "transaction_date": datetime(2026, 5, 31, 23, 59, 59)},
        {"product_type": "Cuenta Ahorro"},
        {"transaction_status": "Declined"},
        {"transaction_status": "Pending"},
        {"transaction_date": datetime(2026, 3, 2, 23, 59, 59)},
        {"transaction_date": datetime(2026, 6, 1, 0, 0)},
        {"currency": "EUR"},                                # no tier in amount_gate: not a candidate
        {"customer_id": TRAIN},
        *({flag: True} for flag in QC),
    ])
    assert {row["transaction_id"] for row in out} == {"TRX-KEEP", "TRX-FIRST-DAY", "TRX-LAST-DAY"}


def test_ac_01_maps_country_product_zone_tier_and_neighbours(tmp_path):
    """AC-01: one row per candidate with the columns of §7.2; n_candidates_7d counts the customer's card transactions."""
    out = {row["transaction_id"]: row for row in built(tmp_path, [
        {"transaction_id": "TRX-MX", "fraud_score": 72.0, "amount": 1000.0},
        {"transaction_id": "TRX-MX-NEAR", "transaction_date": datetime(2026, 5, 27, 9, 0), "fraud_score": 30.0,
         "amount": 1000.01, "merchant_name": None},
        {"transaction_id": "TRX-MX-DECLINED", "transaction_date": datetime(2026, 5, 13, 11, 0),
         "transaction_status": "Declined"},
        {"transaction_id": "TRX-MX-FAR", "transaction_date": datetime(2026, 5, 27, 10, 1), "fraud_score": 29.99},
        {"transaction_id": "TRX-MX-SAVINGS", "product_type": "Cuenta Ahorro"},
        {"transaction_id": "TRX-CO", "customer_id": HELDOUT, "customer_country": "Colombia", "currency": "COP",
         "amount": 20000000.01, "fraud_score": None, "product_type": "Tarjeta Débito", "customer_segment": "Student"},
    ])}
    assert set(out) == {"TRX-MX", "TRX-MX-NEAR", "TRX-MX-FAR", "TRX-CO"}
    assert out["TRX-MX"] == {
        "customer_id": DEV, "country": "MX", "segment": "Basic", "split": "dev", "product_id": "PRD-1",
        "product_type": "credit", "transaction_id": "TRX-MX", "transaction_date": "2026-05-20 10:00:00",
        "amount": 1000.0, "currency": "USD", "merchant_name": "TIENDA X", "fraud_score": 72.0, "zone": "high",
        "amount_tier": "low", "n_candidates_7d": 3}          # itself, the near one and the declined one
    near, far, co = out["TRX-MX-NEAR"], out["TRX-MX-FAR"], out["TRX-CO"]
    assert (near["zone"], near["amount_tier"], near["merchant_name"]) == ("medium", "mid", None)
    assert (far["zone"], far["n_candidates_7d"]) == ("human", 2)
    assert (co["country"], co["product_type"], co["split"], co["zone"], co["amount_tier"], co["fraud_score"]) == (
        "CO", "debit", "heldout", "human", "above_high", None)


def test_ac_01_keeps_every_scored_candidate_and_a_fixed_human_sample(tmp_path):
    """AC-01: high and medium candidates are all kept; the human zone keeps 6 per cell, the same on every run."""
    rows = ([{"transaction_id": f"TRX-HIGH-{i}", "fraud_score": 90.0} for i in range(8)]
            + [{"transaction_id": f"TRX-LOW-{i}", "fraud_score": 5.0} for i in range(9)]
            + [{"transaction_id": f"TRX-NULL-{i}", "fraud_score": None} for i in range(9)])
    out = built(tmp_path, rows)
    kinds = [row["transaction_id"].rsplit("-", 1)[0] for row in out]
    assert (kinds.count("TRX-HIGH"), kinds.count("TRX-LOW"), kinds.count("TRX-NULL")) == (8, 6, 6)
    assert demo_index.build(tmp_path)[1] == demo_index.build(tmp_path)[1]


def test_ac_01_committed_index_matches_the_query_layout_and_the_policies():
    """AC-01: eval/demo_index.csv has the columns of §7.2 and its zone and tier are the policy engine's."""
    engine = PolicyEngine.load()
    assert list(ROWS[0]) == COLUMNS and len(ROWS) > 100
    assert len({row["transaction_id"] for row in ROWS}) == len(ROWS)
    order = [(row["country"], row["split"], row["zone"], row["product_type"], row["transaction_id"]) for row in ROWS]
    assert order == sorted(order)
    for row in ROWS:
        score = float(row["fraud_score"]) if row["fraud_score"] else None
        assert row["country"] in ("MX", "CO", "AR") and row["product_type"] in ("debit", "credit")
        assert "2026-03-03 00:00:00" <= row["transaction_date"] < "2026-06-01 00:00:00"
        assert row["zone"] == ("human" if score is None else "high" if score >= 50 else "medium" if score >= 30
                               else "human")
        assert row["amount_tier"] == TIER[engine.amount_tier(float(row["amount"]), row["currency"], row["country"])]
        assert int(row["n_candidates_7d"]) >= 1
    zones = engine.policies.zones
    assert (zones["high"].score_min, zones["medium"].score_min) == (50, 30)


def test_ac_01_every_country_and_split_has_candidates_in_the_human_zone():
    """AC-01: candidates per country x zone x split; the cells gold leaves empty are listed in eval/README.md."""
    cells = {(row["country"], row["zone"], row["split"]) for row in ROWS}
    readme = (ROOT / "eval/README.md").read_text(encoding="utf-8")
    for country in ("MX", "CO", "AR"):
        for split in ("dev", "heldout"):
            assert (country, "human", split) in cells
            for zone in ("high", "medium"):
                assert (country, zone, split) in cells or f"| {country} | {zone} | {split} | 0 |" in readme


@pytest.mark.parametrize("customer_id", [DEV, HELDOUT, TRAIN, "CLI-HBQWV3L8TBI3", "CLI-Y0L7FZFOF0AZ", "cliente ñ"])
def test_ac_07_sql_split_equals_the_python_reference(tmp_path, customer_id):
    """AC-07 (§7.1): the split expression of the query and customer_split() agree; train customers are left out."""
    out = built(tmp_path, [{"customer_id": customer_id}])
    expected = demo_index.customer_split(customer_id)
    assert [row["split"] for row in out] == ([] if expected == "train" else [expected])


def test_ac_07_committed_index_has_each_customer_in_one_split():
    """AC-07: every row carries the split of its customer, so no customer or transaction is in both sets."""
    assert {demo_index.customer_split(DEV), demo_index.customer_split(HELDOUT),
            demo_index.customer_split(TRAIN)} == {"dev", "heldout", "train"}
    assert all(row["split"] == demo_index.customer_split(row["customer_id"]) for row in ROWS)
    assert {row["split"] for row in ROWS} == {"dev", "heldout"}


def test_ac_08_query_script_and_index_never_touch_the_labels():
    """AC-08: the query, the script and the index never read data/gold_eval/ nor contain is_fraud."""
    for path in ("queries/eval/demo_index.sql", "eval/demo_index.py", "eval/demo_index.csv"):
        text = (ROOT / path).read_text(encoding="utf-8").lower()
        assert "gold_eval" not in text and "is_fraud" not in text and "transaction_labels" not in text, path
