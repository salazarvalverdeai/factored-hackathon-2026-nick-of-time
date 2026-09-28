"""Silver: bronze tipado según el contrato, con dedup/upsert por PK y validación pandera.

Pasos por tabla (cada uno deja un conteo en el resultado):
1. Renombres declarados (contracts.ALIASES): el alias alimenta la columna canónica.
2. Normalización de etiquetas (contracts.NORMALIZE), p. ej. `Mexico` → `México`; se cuenta antes de corregir.
3. Cast con TRY_CAST al tipo del contrato; un valor no nulo que no castea es un "cast fallido" (queda nulo).
4. Dedup: filas idénticas en todas las columnas del contrato = duplicado exacto; misma PK con contenido distinto =
   versiones (upsert: gana process_date más reciente, luego la carga más reciente, luego la clave de archivo).
5. Rezago de llegada en hechos: `_lag_days = process_date − fecha del evento` (> 0 = llegada tardía).
6. Contrato pandera: las filas que lo violan van a silver/_quarantine/<tabla>.parquet con el motivo.
"""
from __future__ import annotations

import logging

import duckdb
import polars as pl
from pandera.errors import SchemaErrors

from data.pipeline import contracts
from data.pipeline.config import Layout

log = logging.getLogger("pipeline.silver")


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _raw_exprs(table: str, bronze_cols: list[str]) -> tuple[dict[str, str], list[str], dict[str, str]]:
    """Expresión VARCHAR de cada columna canónica, columnas faltantes y alias usados."""
    aliases = contracts.ALIASES.get(table, {})
    exprs, missing, used = {}, [], {}
    for col in contracts.columns(table):
        srcs = [col] if col in bronze_cols else []
        for alias, canon in aliases.items():
            if canon == col and alias in bronze_cols:
                srcs.append(alias)
                used[alias] = col
        if not srcs:
            exprs[col] = "NULL::VARCHAR"
            missing.append(col)
        else:
            exprs[col] = q(srcs[0]) if len(srcs) == 1 else f"coalesce({', '.join(q(s) for s in srcs)})"
    return exprs, missing, used


def _typed_expr(table: str, col: str) -> str:
    raw = f"r.{q(col)}"
    mapping = contracts.NORMALIZE.get(table, {}).get(col)
    if mapping:
        cases = " ".join(f"WHEN {lit(a)} THEN {lit(b)}" for a, b in mapping.items())
        raw = f"(CASE {raw} {cases} ELSE {raw} END)"
    return f"TRY_CAST({raw} AS {contracts.duckdb_type(table, col)}) AS {q(col)}"


def _contract_failures(table: str, df: pl.DataFrame) -> tuple[list[dict], dict[int, str]]:
    """Valida con pandera. Devuelve (fallas agregadas por columna y check, motivo por índice de fila)."""
    cols = contracts.columns(table)
    try:
        contracts.SCHEMAS[table].validate(df.select(cols), lazy=True)
        return [], {}
    except SchemaErrors as e:
        fc = e.failure_cases
    schema_level = fc.filter(pl.col("index").is_null())
    if schema_level.height:
        raise RuntimeError(f"{table}: el contrato falla a nivel de schema:\n{schema_level}")
    summary = (fc.group_by("column", "check").agg(pl.len().alias("n"), pl.col("index").n_unique().alias("rows"))
               .sort("column", "check"))
    reasons = (fc.group_by("index").agg(pl.concat_str([pl.col("column"), pl.col("check")], separator=":")
                                        .unique().sort().str.join("; ").alias("reason")))
    return summary.to_dicts(), dict(zip(reasons["index"].to_list(), reasons["reason"].to_list()))


def build_table(con: duckdb.DuckDBPyConnection, table: str, layout: Layout) -> dict:
    bronze = layout.bronze / f"{table}.parquet"
    pk = contracts.PRIMARY_KEY[table]
    cols = contracts.columns(table)
    bronze_cols = [c[0] for c in con.sql(f"DESCRIBE SELECT * FROM read_parquet('{bronze}')").fetchall()]
    exprs, missing, used = _raw_exprs(table, bronze_cols)
    con.execute(f"""CREATE OR REPLACE TEMP VIEW _raw AS
        SELECT {', '.join(f'{e} AS {q(c)}' for c, e in exprs.items())}, _source_key, _loaded_at, _partition_date
        FROM read_parquet('{bronze}')""")

    # Conteos previos al tipado: alias usados, etiquetas a normalizar, cast fallidos
    renamed = {a: con.sql(f"SELECT count({q(a)}) FROM read_parquet('{bronze}')").fetchone()[0] for a in used}
    normalized = {}
    for col, mapping in contracts.NORMALIZE.get(table, {}).items():
        values = ", ".join(lit(v) for v in [*mapping, *mapping.values()])
        n, den = con.sql(f"""SELECT count(*) FILTER (WHERE {q(col)} IN ({', '.join(lit(a) for a in mapping)})),
                                    count(*) FILTER (WHERE {q(col)} IN ({values})) FROM _raw""").fetchone()
        normalized[col] = {"mapping": mapping, "n": n, "denominator": den}
    cast_sql = ", ".join(
        f"count(*) FILTER (WHERE {q(c)} IS NOT NULL AND TRY_CAST({q(c)} AS {contracts.duckdb_type(table, c)}) IS NULL)"
        for c in cols)
    cast_failures = {c: n for c, n in zip(cols, con.sql(f"SELECT {cast_sql} FROM _raw").fetchone()) if n}

    # Tipado + normalización + dedup/upsert
    norm_cols = [c for c in contracts.NORMALIZE.get(table, {})]
    norm_flag = " OR ".join(f"coalesce(r.{q(c)} IN ({', '.join(lit(a) for a in contracts.NORMALIZE[table][c])}), false)"
                            for c in norm_cols) or "false"
    order = ["process_date DESC NULLS LAST"] if "process_date" in cols else []
    order += ["_loaded_at DESC", "_source_key DESC"]
    con.execute(f"""CREATE OR REPLACE TEMP TABLE _typed AS
        SELECT {', '.join(_typed_expr(table, c) for c in cols)},
               {norm_flag} AS _qc_normalized, r._source_key, r._loaded_at, r._partition_date
        FROM _raw r""")
    col_list = ", ".join(q(c) for c in cols)
    # Duplicados y versiones solo entre filas con PK; las de PK nula pasan tal cual (el contrato las pone en cuarentena)
    n_rows, n_keyed, n_distinct, n_pk = con.sql(f"""
        SELECT count(*), count({q(pk)}),
               (SELECT count(*) FROM (SELECT DISTINCT {col_list} FROM _typed WHERE {q(pk)} IS NOT NULL)),
               count(DISTINCT {q(pk)})
        FROM _typed""").fetchone()
    event = contracts.EVENT_DATE.get(table)
    lag = f", date_diff('day', {q(event)}::DATE, process_date) AS _lag_days" if event else ""
    con.execute(f"""CREATE OR REPLACE TEMP TABLE _dedup AS
        SELECT * EXCLUDE (_rn) {lag}
        FROM (SELECT *, CASE WHEN {q(pk)} IS NULL THEN 1
                             ELSE row_number() OVER (PARTITION BY {q(pk)} ORDER BY {', '.join(order)}) END AS _rn
              FROM _typed)
        WHERE _rn = 1
        ORDER BY {q(pk)}""")
    required_null = " OR ".join(f"{q(c)} IS NULL" for c in contracts.required_columns(table))
    n_required_null = con.sql(f"SELECT count(*) FILTER (WHERE {required_null}) FROM _dedup").fetchone()[0]

    # Contrato pandera
    df = con.sql("SELECT * FROM _dedup").pl()
    failures, reasons = _contract_failures(table, df)
    bad = list(reasons)
    df = df.with_row_index("_idx").with_columns(pl.col("_idx").cast(pl.Int64))
    quarantine = df.filter(pl.col("_idx").is_in(bad)).with_columns(
        pl.col("_idx").replace_strict(reasons, default=None, return_dtype=pl.Utf8).alias("_quarantine_reason")
    ).drop("_idx")
    silver = df.filter(~pl.col("_idx").is_in(bad)).drop("_idx")
    silver.write_parquet(layout.silver / f"{table}.parquet", compression="zstd")
    qpath = layout.quarantine / f"{table}.parquet"
    if quarantine.height:
        quarantine.write_parquet(qpath, compression="zstd")
    elif qpath.exists():
        qpath.unlink()

    late = {}
    if event:
        late = {"n_late": int(silver.filter(pl.col("_lag_days") > 0).height),
                "max_lag_days": silver["_lag_days"].max(),
                "lag_hist": {str(k): v for k, v in silver.group_by("_lag_days").len().sort("_lag_days").iter_rows()},
                "partition_mismatch": int(silver.filter(pl.col("_partition_date") != pl.col("process_date")).height),
                "denominator": silver.height}
    nulls = {c: int(silver[c].null_count()) for c in cols}
    result = {
        "rows_bronze": n_rows, "exact_duplicates": n_keyed - n_distinct, "superseded_versions": n_distinct - n_pk,
        "null_pk_rows": n_rows - n_keyed, "rows_after_dedup": n_pk + (n_rows - n_keyed),
        "required_null_rows": n_required_null, "quarantined": quarantine.height, "rows_silver": silver.height,
        "missing_columns": missing, "renamed": {f"{a}->{used[a]}": n for a, n in renamed.items()},
        "extra_columns": [c for c in bronze_cols if c not in cols and c not in used and not c.startswith("_")],
        "normalized": normalized, "cast_failures": cast_failures, "contract_failures": failures,
        "contract_checks": sum(len(c.checks) + (not c.nullable) + c.unique
                               for c in contracts.SCHEMAS[table].columns.values()),
        "late": late, "nulls": nulls,
    }
    log.info("silver %s: %s → %s filas (dup exactos %d, versiones %d, cuarentena %d)", table, f"{n_rows:,}",
             f"{silver.height:,}", result["exact_duplicates"], result["superseded_versions"], quarantine.height)
    return result
