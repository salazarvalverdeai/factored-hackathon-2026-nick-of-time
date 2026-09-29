"""Quality checks with counts: one row per check with violations, denominator and %.

Two sources:
- Gold flags (gold.FLAGS): orphan FKs, FKs to another customer's products, future dates, transactions before the
  product opening and late arrivals. n = rows with the flag true; denominator = rows where the check applies.
- Bronze/silver steps: exact duplicates, PK versions, nulls in required columns, failed casts, contract
  quarantine, normalized labels (México/Mexico) and files with a schema change.

When it exists, the EDA figure for the same check is attached (outputs/tables/01_*.csv), to show that the pipeline
reproduces what was measured in data_quality.md. transactions is not compared: the EDA covers the 3 years and gold only
the 12-month window (contracts/gold_contract.md, R1). The EDA tables are not in this repo, so the column stays empty.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

import duckdb

from data.pipeline.config import EDA_TABLES_DIR, TX_WINDOW, Layout

log = logging.getLogger("pipeline.checks")

# (id, table, flag, check, description, action, EDA reference)
FLAG_CHECKS = [
    ("FK-01", "products", "qc_customer_orphan", "orphan FK", "customer_id with no row in customers",
     "flag in gold", ("fk", "products", "customer_id")),
    ("FK-02", "transactions", "qc_customer_orphan", "orphan FK",
     "resolved customer_id (product owner) with no row in customers", "flag in gold", None),
    ("FK-03", "transactions", "qc_product_orphan", "orphan FK", "product_id with no row in products",
     "flag in gold", ("fk", "transactions", "product_id")),
    ("FK-04", "complaints", "qc_customer_orphan", "orphan FK", "customer_id with no row in customers",
     "flag in gold", ("fk", "complaints", "customer_id")),
    ("FK-05", "complaints", "qc_affected_product_orphan", "orphan FK",
     "affected_product_id with no row in products", "flag in gold", ("fk", "complaints", "affected_product_id")),
    ("OWN-01", "transactions", "qc_product_other_customer", "FK to another customer's product",
     "the file's customer_id is not the product owner", "gold uses the owner (R2); flag for audit",
     ("consistency", "transactions", "C12")),
    ("OWN-02", "complaints", "qc_affected_product_other_customer", "FK to another customer's product",
     "affected_product_id belongs to another customer", "flag in gold; the serving layer does not show it",
     ("consistency", "complaints", "C15")),
    ("FUT-01", "customers", "qc_future_last_updated", "future date",
     "last_updated after the file's load day", "flag in gold", ("range", "customers", "R52")),
    ("FUT-02", "products", "qc_future_last_updated", "future date",
     "last_updated after the file's load day", "flag in gold", ("range", "products", "R61")),
    ("FUT-03", "transactions", "qc_future_date", "future date",
     "transaction_date after the file's load day", "flag in gold", None),
    ("FUT-04", "complaints", "qc_future_date", "future date",
     "creation_date after the file's load day", "flag in gold", None),
    ("ORD-01", "transactions", "qc_before_product_open", "transaction before opening",
     "transaction_date before products.opening_date", "flag in gold", ("consistency", "transactions", "C13")),
    ("LATE-01", "transactions", "qc_late_arrival", "late arrival", "process_date − transaction_date > 0 days",
     "flag in gold; freshness alert", None),
    ("LATE-02", "complaints", "qc_late_arrival", "late arrival", "process_date − creation_date > 0 days",
     "flag in gold; freshness alert", None),
]
LABEL_EDA: dict = {}
WINDOWED = {"transactions"}  # no comparison with the EDA: different time coverage


def _read(name: str) -> list[dict]:
    path = EDA_TABLES_DIR / name
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def eda_reference(ref: tuple | None) -> dict | None:
    """EDA figure for the same check: {n, denominator, source} or None."""
    if ref is None:
        return None
    kind, table, key = ref
    if kind in ("consistency", "range"):
        name = f"01_{kind}_checks.csv"
        for r in _read(name):
            if r["tbl"] == table and r["check_id"] == key:
                return {"n": int(r["n_violations"]), "denominator": int(r["n_checked"]), "source": f"{name} ({key})"}
    if kind == "fk":
        for r in _read("01_fk_orphans.csv"):
            if r["child"] == table and r["fk"] == key:
                return {"n": int(r["n_orphans"]), "denominator": int(r["n_with_fk"]), "source": "01_fk_orphans.csv"}
    if kind == "dup":
        for r in _read("01_quality_summary.csv"):
            if r["table"] == table:
                return {"n": int(r["dup_exact"]), "denominator": int(r["n_rows"]), "source": "01_quality_summary.csv"}
    return None


def _row(cid, table, check, desc, n, den, action, eda=None) -> dict:
    return {"id": cid, "table": table, "check": check, "description": desc, "n": int(n), "denominator": int(den),
            "pct": round(100.0 * n / den, 3) if den else None, "action": action, "eda": eda_reference(eda)}


def run(con: duckdb.DuckDBPyConnection, layout: Layout, tables: tuple[str, ...], silver: dict,
        registry: list[dict], with_eda: bool = True) -> list[dict]:
    out = []
    for t in tables:
        s = silver[t]
        out.append(_row("DUP-01", t, "exact duplicate", "rows identical in all contract columns",
                        s["exact_duplicates"], s["rows_bronze"], "one is kept", ("dup", t, None)))
        out.append(_row("DUP-02", t, "PK versions", "same PK with different content (upsert)",
                        s["superseded_versions"], s["rows_bronze"], "latest process_date / load wins"))
        out.append(_row("NUL-01", t, "null in required column", "rows with a null in some required column",
                        s["required_null_rows"], s["rows_after_dedup"], "quarantine (contract)"))
        out.append(_row("CAST-01", t, "failed cast", "non-null values that do not cast to the contract type",
                        sum(s["cast_failures"].values()), s["rows_bronze"], "left null; quarantine if required"))
        out.append(_row("CON-01", t, "violates the contract", "rows that fail some pandera check",
                        s["quarantined"], s["rows_after_dedup"], "silver/_quarantine/"))
        for col, norm in s["normalized"].items():
            pairs = ", ".join(f"{a} → {b}" for a, b in norm["mapping"].items())
            out.append(_row("LBL-01", t, "inconsistent label", f"{col}: {pairs}", norm["n"], norm["denominator"],
                            "normalized in silver", LABEL_EDA.get((t, col))))
        files = [r for r in registry if r["table"] == t]
        out.append(_row("SCH-01", t, "schema change", "files whose header differs from the contract",
                        sum(r["schema_drift"] for r in files), len(files), "declared alias or column only in bronze"))
    if "transactions" in tables:
        n, den = con.sql(f"""SELECT count(*) FILTER (WHERE NOT (transaction_date >= TIMESTAMP '{TX_WINDOW[0]}'
                                                         AND transaction_date < TIMESTAMP '{TX_WINDOW[1]}')), count(*)
                             FROM read_parquet('{layout.silver / 'transactions.parquet'}')""").fetchone()
        out.append(_row("WIN-01", "transactions", "outside the window",
                        f"transaction_date outside [{TX_WINDOW[0]}, {TX_WINDOW[1]}) in what was read",
                        n, den, "stays in silver, does not go to gold (R1)"))
    for cid, t, flag, check, desc, action, eda in FLAG_CHECKS:
        if t not in tables:
            continue
        n, den = con.sql(f"SELECT count(*) FILTER (WHERE {flag}), count({flag}) "
                         f"FROM read_parquet('{layout.gold / f'{t}.parquet'}')").fetchone()
        out.append(_row(cid, t, check, desc, n, den, action, eda))
    for r in out:
        if not with_eda or r["table"] in WINDOWED:
            r["eda"] = None
    log.info("checks: %d, with violations: %d", len(out), sum(r["n"] > 0 for r in out))
    return out
