"""Gold per contracts/gold_contract.md: silver + quality flags, derived tables and labels kept apart.

data/gold/       customers, products, complaints (complete); transactions (12-month window, R1; `customer_id`
                 resolved by join with products, R2; without `is_fraud`, R3); customer_profile and
                 transactions_enriched (R4)
data/gold_eval/  transaction_labels (transaction_id, is_fraud) for the same transactions as gold (R3)

The `qc_*` flags are booleans, null when the check does not apply (e.g. a complaint with no affected product). The
counts in checks.py are aggregations of these flags: the definition of each check lives in a single place (FLAGS).

Nothing is deleted in gold: a row with a quality problem is flagged and the serving layer decides. Rows that violate
the silver contract do not get here (they stay in silver/_quarantine/).

Everything is written first to `_staging/`. Before publishing, the contract rules G1–G5 are verified: if one fails,
the run stops and gold stays as it was. Then each table is compared with the previous version by PK (inserted,
updated, deleted, unchanged) and the manifest version goes up only if the sha256 of some table changed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime, timezone

import duckdb

from data.pipeline import contracts
from data.pipeline.config import GOLD_CONTRACT, LOAD_TZ, PIPELINE_VERSION, ROOT, TX_WINDOW, Layout

log = logging.getLogger("pipeline.gold")

DERIVED = ("customer_profile", "transactions_enriched")
EVAL = ("transaction_labels",)
PK = {**contracts.PRIMARY_KEY, "customer_profile": "customer_id", "transactions_enriched": "transaction_id",
      "transaction_labels": "transaction_id"}
# Columns the contract forbids in data/gold/ (R3)
FORBIDDEN_IN_GOLD = ("is_fraud",)


def in_window(col: str, alias: str = "x") -> str:
    return f"({alias}.{col} >= TIMESTAMP '{TX_WINDOW[0]}' AND {alias}.{col} < TIMESTAMP '{TX_WINDOW[1]}')"


def _future(col: str, alias: str) -> str:
    """Date after the file's load day (in LOAD_TZ). Null if the date is null."""
    return f"({alias}.{col}::DATE > timezone('{LOAD_TZ}', {alias}._loaded_at)::DATE)"


# Flags per table: name → SQL expression over the FROM aliases of gold_select
FLAGS: dict[str, dict[str, str]] = {
    "customers": {
        "qc_future_last_updated": _future("last_updated", "x"),
    },
    "products": {
        "qc_customer_orphan": "(c.customer_id IS NULL)",
        "qc_future_last_updated": _future("last_updated", "x"),
    },
    "transactions": {
        # c is joined on the product owner (R2): the resolved customer does not exist in customers
        "qc_customer_orphan": "CASE WHEN p.product_id IS NOT NULL THEN c.customer_id IS NULL END",
        "qc_product_orphan": "(p.product_id IS NULL)",
        # the file's customer_id does not match the product owner (gold uses the owner)
        "qc_product_other_customer": "CASE WHEN p.product_id IS NOT NULL THEN x.customer_id <> p.customer_id END",
        "qc_before_product_open": "CASE WHEN p.product_id IS NOT NULL THEN x.transaction_date::DATE < p.opening_date END",
        "qc_future_date": _future("transaction_date", "x"),
        "qc_late_arrival": "(x._lag_days > 0)",
    },
    "complaints": {
        "qc_customer_orphan": "(c.customer_id IS NULL)",
        "qc_affected_product_orphan": "CASE WHEN x.affected_product_id IS NOT NULL THEN p.product_id IS NULL END",
        "qc_affected_product_other_customer":
            "CASE WHEN p.product_id IS NOT NULL THEN x.customer_id <> p.customer_id END",
        "qc_future_date": _future("creation_date", "x"),
        "qc_late_arrival": "(x._lag_days > 0)",
    },
}
JOINS = {
    "customers": "",
    "products": "LEFT JOIN s_customers c ON c.customer_id = x.customer_id",
    "transactions": "LEFT JOIN s_products p ON p.product_id = x.product_id "
                    "LEFT JOIN s_customers c ON c.customer_id = p.customer_id",
    "complaints": "LEFT JOIN s_customers c ON c.customer_id = x.customer_id "
                  "LEFT JOIN s_products p ON p.product_id = x.affected_product_id",
}
WHERE = {"transactions": f"WHERE {in_window('transaction_date')}"}
LINEAGE = ["_source_key", "_loaded_at", "_partition_date"]


def gold_select(table: str) -> str:
    cols = []
    for c in contracts.columns(table):
        if c in FORBIDDEN_IN_GOLD:
            continue
        cols.append("p.customer_id AS customer_id" if (table, c) == ("transactions", "customer_id") else f"x.{c}")
    flags = [f"{expr} AS {name}" for name, expr in FLAGS[table].items()]
    if contracts.NORMALIZE.get(table):
        flags.append("x._qc_normalized AS qc_label_normalized")
    lineage = [f"x.{c}" for c in LINEAGE] + (["x._lag_days"] if table in contracts.EVENT_DATE else [])
    if table == "transactions":
        lineage.append("x.customer_id AS _customer_id_source")
    return (f"SELECT {', '.join(cols + flags + lineage)} FROM s_{table} x {JOINS[table]} {WHERE.get(table, '')} "
            f"ORDER BY x.{contracts.PRIMARY_KEY[table]}")


def labels_select() -> str:
    return f"SELECT x.transaction_id, x.is_fraud FROM s_transactions x WHERE {in_window('transaction_date')} " \
           "ORDER BY x.transaction_id"


def enriched_select(con: duckdb.DuckDBPyConnection) -> str:
    content = [c[0] for c in con.sql("DESCRIBE SELECT * FROM g_transactions").fetchall() if not c[0].startswith("_")]
    return (f"SELECT {', '.join(f't.{c}' for c in content)}, p.product_type, p.product_status, "
            "p.opening_date AS product_opening_date, c.country AS customer_country, c.segment AS customer_segment "
            "FROM g_transactions t LEFT JOIN g_products p ON p.product_id = t.product_id "
            "LEFT JOIN g_customers c ON c.customer_id = t.customer_id ORDER BY t.transaction_id")


PROFILE_SELECT = f"""
    WITH tx AS (SELECT customer_id, count(*) AS n,
                       count(*) FILTER (WHERE transaction_status = 'Declined') AS n_declined,
                       count(*) FILTER (WHERE transaction_status = 'Reversed') AS n_reversed,
                       min(transaction_date) AS first_at, max(transaction_date) AS last_at
                FROM g_transactions WHERE customer_id IS NOT NULL GROUP BY customer_id),
         pr AS (SELECT customer_id, count(*) AS n, count(*) FILTER (WHERE product_status = 'Active') AS n_active
                FROM g_products GROUP BY customer_id),
         cm AS (SELECT x.customer_id, count(*) AS n FROM g_complaints x WHERE {in_window('creation_date')}
                GROUP BY x.customer_id)
    SELECT c.customer_id, c.country, c.segment, c.customer_status, c.registration_date,
           coalesce(pr.n, 0) AS n_products, coalesce(pr.n_active, 0) AS n_active_products,
           coalesce(tx.n, 0) AS n_transactions_12m, coalesce(tx.n_declined, 0) AS n_declined_12m,
           coalesce(tx.n_reversed, 0) AS n_reversed_12m, tx.first_at AS first_transaction_at_12m,
           tx.last_at AS last_transaction_at_12m, coalesce(cm.n, 0) AS n_complaints_12m, c.qc_future_last_updated
    FROM g_customers c LEFT JOIN tx USING (customer_id) LEFT JOIN pr USING (customer_id) LEFT JOIN cm USING (customer_id)
    ORDER BY c.customer_id"""


def contract_checks(con: duckdb.DuckDBPyConnection, gold_tables: list[str]) -> list[dict]:
    """Rules G1–G5 of contracts/gold_contract.md over the g_* views (staging)."""
    out = []

    def add(rid: str, rule: str, value, ok: bool) -> None:
        out.append({"id": rid, "rule": rule, "value": value, "ok": bool(ok)})

    with_forbidden = [t for t in gold_tables for c in con.sql(f"DESCRIBE SELECT * FROM g_{t}").fetchall()
                      if c[0] in FORBIDDEN_IN_GOLD]
    add("G1", "no table in data/gold/ has is_fraud", with_forbidden or "none", not with_forbidden)
    lo, hi, n_out = con.sql(f"""SELECT min(transaction_date)::VARCHAR, max(transaction_date)::VARCHAR,
                                       count(*) FILTER (WHERE NOT {in_window('transaction_date', 'g_transactions')})
                                FROM g_transactions""").fetchone()
    add("G2", f"transaction_date in [{TX_WINDOW[0]}, {TX_WINDOW[1]})", f"{lo} → {hi}; outside: {n_out}", n_out == 0)
    n = con.sql("""SELECT count(*) FROM g_transactions t JOIN g_products p USING (product_id)
                   WHERE t.customer_id IS DISTINCT FROM p.customer_id""").fetchone()[0]
    add("G3", "transactions.customer_id = product owner (join)", f"{n} differing rows", n == 0)
    a, b = con.sql("""SELECT (SELECT count(*) FROM g_transactions t ANTI JOIN g_transaction_labels l USING (transaction_id)),
                             (SELECT count(*) FROM g_transaction_labels l ANTI JOIN g_transactions t USING (transaction_id))
                   """).fetchone()
    add("G4", "transaction_labels 1:1 with gold.transactions", f"without label: {a}; label without transaction: {b}",
        a == 0 and b == 0)
    pc, pu, cc, ec, eu, tc = con.sql("""SELECT (SELECT count(*) FROM g_customer_profile),
                                               (SELECT count(DISTINCT customer_id) FROM g_customer_profile),
                                               (SELECT count(*) FROM g_customers),
                                               (SELECT count(*) FROM g_transactions_enriched),
                                               (SELECT count(DISTINCT transaction_id) FROM g_transactions_enriched),
                                               (SELECT count(*) FROM g_transactions)""").fetchone()
    add("G5", "customer_profile 1 row per customer; transactions_enriched 1 per transaction",
        f"profile {pc} (unique {pu}) vs customers {cc}; enriched {ec} (unique {eu}) vs transactions {tc}",
        pc == pu == cc and ec == eu == tc)
    return out


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def diff(con: duckdb.DuckDBPyConnection, pk: str, old: str, new: str) -> dict:
    """Changes by PK between two versions of a table (content = columns without `_*` lineage)."""
    content = [c for c in con.sql(f"DESCRIBE SELECT * FROM read_parquet('{new}')").fetchall() if not c[0].startswith("_")]
    old_cols = {c[0] for c in con.sql(f"DESCRIBE SELECT * FROM read_parquet('{old}')").fetchall()}
    cols = [c[0] for c in content if c[0] in old_cols]
    h = f"hash({', '.join(cols)})"
    row = con.sql(f"""
        WITH o AS (SELECT {pk} AS k, {h} AS h FROM read_parquet('{old}')),
             n AS (SELECT {pk} AS k, {h} AS h FROM read_parquet('{new}'))
        SELECT count(*) FILTER (WHERE o.k IS NULL), count(*) FILTER (WHERE o.k IS NOT NULL AND n.k IS NOT NULL AND o.h <> n.h),
               count(*) FILTER (WHERE n.k IS NULL), count(*) FILTER (WHERE o.h = n.h)
        FROM o FULL OUTER JOIN n ON o.k = n.k""").fetchone()
    return dict(zip(["inserted", "updated", "deleted", "unchanged"], row))


def build(con: duckdb.DuckDBPyConnection, layout: Layout, tables: tuple[str, ...], source: dict) -> dict:
    for t in tables:
        con.execute(f"CREATE OR REPLACE VIEW s_{t} AS SELECT * FROM read_parquet('{layout.silver / f'{t}.parquet'}')")
    stage = {"gold": layout.gold / "_staging", "gold_eval": layout.gold_eval / "_staging"}
    final = {"gold": layout.gold, "gold_eval": layout.gold_eval}
    for d in stage.values():
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    previous = json.loads(layout.manifest.read_text()) if layout.manifest.exists() else None

    plan: list[tuple[str, str, str]] = [(t, "gold", gold_select(t)) for t in tables] + [(EVAL[0], "gold_eval", labels_select())]
    layer_of = {}
    for name, layer, sql in plan:
        path = stage[layer] / f"{name}.parquet"
        con.execute(f"COPY ({sql}) TO '{path}' (FORMAT parquet, COMPRESSION zstd)")
        con.execute(f"CREATE OR REPLACE VIEW g_{name} AS SELECT * FROM read_parquet('{path}')")
        layer_of[name] = layer
    for name, sql in [("transactions_enriched", enriched_select(con)), ("customer_profile", PROFILE_SELECT)]:
        path = stage["gold"] / f"{name}.parquet"
        con.execute(f"COPY ({sql}) TO '{path}' (FORMAT parquet, COMPRESSION zstd)")
        con.execute(f"CREATE OR REPLACE VIEW g_{name} AS SELECT * FROM read_parquet('{path}')")
        layer_of[name] = "gold"

    gold_tables = [n for n, layer in layer_of.items() if layer == "gold"]
    rules = contract_checks(con, gold_tables)
    failed = [r for r in rules if not r["ok"]]
    if failed:
        raise RuntimeError(f"gold does not comply with {GOLD_CONTRACT.relative_to(ROOT)}: {failed} (staging not published)")

    tables_meta, diffs = {}, {}
    for name, layer in layer_of.items():
        new, old = stage[layer] / f"{name}.parquet", final[layer] / f"{name}.parquet"
        if old.exists():
            diffs[name] = diff(con, PK[name], str(old), str(new))
        else:
            n = con.sql(f"SELECT count(*) FROM read_parquet('{new}')").fetchone()[0]
            diffs[name] = {"inserted": n, "updated": 0, "deleted": 0, "unchanged": 0}
        described = con.sql(f"DESCRIBE SELECT * FROM read_parquet('{new}')").fetchall()
        tables_meta[name] = {"layer": layer, "path": f"{layer}/{name}.parquet",
                             "rows": con.sql(f"SELECT count(*) FROM read_parquet('{new}')").fetchone()[0],
                             "bytes": new.stat().st_size, "sha256": sha256_of(new), "primary_key": PK[name],
                             "columns": {c[0]: c[1] for c in described}}
    for name, layer in layer_of.items():
        shutil.move(stage[layer] / f"{name}.parquet", final[layer] / f"{name}.parquet")
    for d in stage.values():
        d.rmdir()

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prev_hashes = {t: m["sha256"] for t, m in (previous or {}).get("tables", {}).items()}
    changed = [t for t in tables_meta if prev_hashes.get(t) != tables_meta[t]["sha256"]]
    if previous is None:
        version, version_created_at = 1, now
    elif changed:
        version, version_created_at = previous["version"] + 1, now
    else:
        version, version_created_at = previous["version"], previous["version_created_at"]
    manifest = {
        "dataset": "latam_bank_gold",
        "version": version,
        "version_created_at": version_created_at,
        "run_at": now,
        "pipeline_version": PIPELINE_VERSION,
        "contract": {"file": GOLD_CONTRACT.relative_to(ROOT).as_posix(), "version": contracts.CONTRACT_VERSION,
                     "transactions_window": list(TX_WINDOW), "rules": rules},
        "source": source,
        "tables": tables_meta,
        "changed_tables": changed,
        "previous": None if previous is None else {"version": previous["version"], "run_at": previous["run_at"],
                                                   "sha256": prev_hashes},
    }
    layout.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    log.info("gold v%d: %s (changed: %s)", version,
             ", ".join(f"{t} {m['rows']:,}" for t, m in tables_meta.items()), ", ".join(changed) or "none")
    return {"manifest": manifest, "diff": diffs, "contract_rules": rules}

