"""El pipeline completo sobre el fixture late_arrival reproduce los conteos de fixture.json → expected y cumple
contracts/gold_contract.md (ventana, customer_id resuelto por join, is_fraud solo en gold_eval, tablas derivadas)."""
from __future__ import annotations

import duckdb

from data.pipeline.config import FIXTURE_DIR, Layout
from data.pipeline.run import expected_vs_actual, run_fixture


def test_fixture_deliveries_match_expected(tmp_path):
    out = run_fixture(tmp_path / "_fixture_run")
    spec = out["spec"]
    assert spec["fixture"] is True and (FIXTURE_DIR / "fixture.json").exists()
    mismatches = [x for d, r in zip(spec["deliveries"], out["runs"])
                  for x in expected_vs_actual(r, spec["expected"][d["name"]]) if not x["ok"]]
    assert mismatches == []
    first, second = (r["gold"]["manifest"] for r in out["runs"])
    assert (first["version"], second["version"]) == (1, 2)
    assert second["source"]["fixture"] is True


def test_gold_contract_on_fixture(tmp_path):
    workdir = tmp_path / "_fixture_run"
    run_fixture(workdir)
    layout, con = Layout(workdir), duckdb.connect()
    gold_cols = {p.stem: {c[0] for c in con.sql(f"DESCRIBE SELECT * FROM read_parquet('{p}')").fetchall()}
                 for p in layout.gold.glob("*.parquet")}
    assert set(gold_cols) == {"customers", "products", "transactions", "complaints", "customer_profile",
                              "transactions_enriched"}
    assert not any("is_fraud" in cols for cols in gold_cols.values())                              # R3
    labels = con.sql(f"SELECT * FROM read_parquet('{layout.gold_eval / 'transaction_labels.parquet'}')").pl()
    assert labels.columns == ["transaction_id", "is_fraud"]
    tx = con.sql(f"SELECT transaction_id, customer_id, _customer_id_source "
                 f"FROM read_parquet('{layout.gold / 'transactions.parquet'}')").pl()
    by_id = {r["transaction_id"]: r for r in tx.iter_rows(named=True)}
    assert by_id["FX-TRX-0005"]["customer_id"] == "FX-CLI-001"                                    # R2: dueño
    assert by_id["FX-TRX-0005"]["_customer_id_source"] == "FX-CLI-005"
    assert by_id["FX-TRX-0009"]["customer_id"] is None                                            # producto huérfano
    assert "FX-TRX-0015" not in by_id                                                             # R1: fuera de ventana
    assert sorted(labels["transaction_id"]) == sorted(by_id)                                      # 1:1
