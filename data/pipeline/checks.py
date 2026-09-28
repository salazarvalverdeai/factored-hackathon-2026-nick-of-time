"""Checks de calidad con conteos: una fila por check con violaciones, denominador y %.

Dos orígenes:
- Flags de gold (gold.FLAGS): FK huérfanas, FK a productos de otro cliente, fechas futuras, transacciones antes de la
  apertura del producto y llegadas tardías. n = filas con el flag en true; denominador = filas donde el check aplica.
- Pasos de bronze/silver: duplicados exactos, versiones de PK, nulos en obligatorias, cast fallidos, cuarentena del
  contrato, etiquetas normalizadas (México/Mexico) y archivos con cambio de schema.

Cuando existe, se adjunta la cifra del EDA para el mismo check (outputs/tables/01_*.csv), para ver que el pipeline
reproduce lo medido en calidad_datos.md. No se compara transactions: el EDA cubre los 3 años y gold solo la ventana de
12 meses (contracts/gold_contract.md, R1). En este repo no están las tablas del EDA, así que la columna queda vacía.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

import duckdb

from data.pipeline.config import EDA_TABLES_DIR, TX_WINDOW, Layout

log = logging.getLogger("pipeline.checks")

# (id, tabla, flag, check, descripción, acción, referencia EDA)
FLAG_CHECKS = [
    ("FK-01", "products", "qc_customer_orphan", "FK huérfana", "customer_id sin fila en customers",
     "flag en gold", ("fk", "products", "customer_id")),
    ("FK-02", "transactions", "qc_customer_orphan", "FK huérfana",
     "customer_id resuelto (dueño del producto) sin fila en customers", "flag en gold", None),
    ("FK-03", "transactions", "qc_product_orphan", "FK huérfana", "product_id sin fila en products",
     "flag en gold", ("fk", "transactions", "product_id")),
    ("FK-04", "complaints", "qc_customer_orphan", "FK huérfana", "customer_id sin fila en customers",
     "flag en gold", ("fk", "complaints", "customer_id")),
    ("FK-05", "complaints", "qc_affected_product_orphan", "FK huérfana",
     "affected_product_id sin fila en products", "flag en gold", ("fk", "complaints", "affected_product_id")),
    ("OWN-01", "transactions", "qc_product_other_customer", "FK a producto de otro cliente",
     "el customer_id del archivo no es el dueño del producto", "gold usa el dueño (R2); flag para auditoría",
     ("consistency", "transactions", "C12")),
    ("OWN-02", "complaints", "qc_affected_product_other_customer", "FK a producto de otro cliente",
     "affected_product_id pertenece a otro cliente", "flag en gold; la capa de servicio no lo muestra",
     ("consistency", "complaints", "C15")),
    ("FUT-01", "customers", "qc_future_last_updated", "fecha futura",
     "last_updated posterior al día de carga del archivo", "flag en gold", ("range", "customers", "R52")),
    ("FUT-02", "products", "qc_future_last_updated", "fecha futura",
     "last_updated posterior al día de carga del archivo", "flag en gold", ("range", "products", "R61")),
    ("FUT-03", "transactions", "qc_future_date", "fecha futura",
     "transaction_date posterior al día de carga del archivo", "flag en gold", None),
    ("FUT-04", "complaints", "qc_future_date", "fecha futura",
     "creation_date posterior al día de carga del archivo", "flag en gold", None),
    ("ORD-01", "transactions", "qc_before_product_open", "transacción antes de la apertura",
     "transaction_date anterior a products.opening_date", "flag en gold", ("consistency", "transactions", "C13")),
    ("LATE-01", "transactions", "qc_late_arrival", "llegada tardía", "process_date − transaction_date > 0 días",
     "flag en gold; alerta de frescura", None),
    ("LATE-02", "complaints", "qc_late_arrival", "llegada tardía", "process_date − creation_date > 0 días",
     "flag en gold; alerta de frescura", None),
]
LABEL_EDA: dict = {}
WINDOWED = {"transactions"}  # sin comparación con el EDA: distinta cobertura temporal


def _read(name: str) -> list[dict]:
    path = EDA_TABLES_DIR / name
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def eda_reference(ref: tuple | None) -> dict | None:
    """Cifra del EDA para el mismo check: {n, denominator, source} o None."""
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
        out.append(_row("DUP-01", t, "duplicado exacto", "filas idénticas en todas las columnas del contrato",
                        s["exact_duplicates"], s["rows_bronze"], "se conserva una", ("dup", t, None)))
        out.append(_row("DUP-02", t, "versiones de PK", "misma PK con contenido distinto (upsert)",
                        s["superseded_versions"], s["rows_bronze"], "gana process_date / carga más reciente"))
        out.append(_row("NUL-01", t, "nulo en obligatoria", "filas con alguna columna obligatoria nula",
                        s["required_null_rows"], s["rows_after_dedup"], "cuarentena (contrato)"))
        out.append(_row("CAST-01", t, "cast fallido", "valores no nulos que no castean al tipo del contrato",
                        sum(s["cast_failures"].values()), s["rows_bronze"], "queda nulo; cuarentena si es obligatoria"))
        out.append(_row("CON-01", t, "viola el contrato", "filas que fallan algún check pandera",
                        s["quarantined"], s["rows_after_dedup"], "silver/_quarantine/"))
        for col, norm in s["normalized"].items():
            pairs = ", ".join(f"{a} → {b}" for a, b in norm["mapping"].items())
            out.append(_row("LBL-01", t, "etiqueta inconsistente", f"{col}: {pairs}", norm["n"], norm["denominator"],
                            "se normaliza en silver", LABEL_EDA.get((t, col))))
        files = [r for r in registry if r["table"] == t]
        out.append(_row("SCH-01", t, "cambio de schema", "archivos cuyo header difiere del contrato",
                        sum(r["schema_drift"] for r in files), len(files), "alias declarado o columna solo en bronze"))
    if "transactions" in tables:
        n, den = con.sql(f"""SELECT count(*) FILTER (WHERE NOT (transaction_date >= TIMESTAMP '{TX_WINDOW[0]}'
                                                         AND transaction_date < TIMESTAMP '{TX_WINDOW[1]}')), count(*)
                             FROM read_parquet('{layout.silver / 'transactions.parquet'}')""").fetchone()
        out.append(_row("WIN-01", "transactions", "fuera de la ventana",
                        f"transaction_date fuera de [{TX_WINDOW[0]}, {TX_WINDOW[1]}) en lo leído",
                        n, den, "queda en silver, no pasa a gold (R1)"))
    for cid, t, flag, check, desc, action, eda in FLAG_CHECKS:
        if t not in tables:
            continue
        n, den = con.sql(f"SELECT count(*) FILTER (WHERE {flag}), count({flag}) "
                         f"FROM read_parquet('{layout.gold / f'{t}.parquet'}')").fetchone()
        out.append(_row(cid, t, check, desc, n, den, action, eda))
    for r in out:
        if not with_eda or r["table"] in WINDOWED:
            r["eda"] = None
    log.info("checks: %d, con violaciones: %d", len(out), sum(r["n"] > 0 for r in out))
    return out
