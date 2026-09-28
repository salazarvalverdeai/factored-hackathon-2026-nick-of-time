"""Bronze: copia fiel de los CSV a Parquet, todo como VARCHAR, con linaje por fila.

Columnas de linaje: `_source_key` (clave estilo S3 del archivo), `_loaded_at` (fecha de carga del archivo) y
`_partition_date` (fecha del nombre `<tabla>_YYYYMMDD.csv`; nula en dimensiones). `union_by_name=true`: una columna que
aparece solo en algunos archivos queda nula en el resto, y bronze la conserva aunque el contrato no la tenga.

Por archivo se compara el header con el contrato: columnas agregadas (no están en el contrato), faltantes y
renombradas (alias declarado en contracts.ALIASES).
"""
from __future__ import annotations

import logging

import duckdb
import polars as pl

from data.pipeline import contracts
from data.pipeline.config import Layout
from data.pipeline.sources import SourceFile

log = logging.getLogger("pipeline.bronze")


def header_diff(table: str, header: list[str]) -> dict:
    expected = set(contracts.columns(table))
    aliases = contracts.ALIASES.get(table, {})
    renamed = {a: aliases[a] for a in header if a in aliases}
    present = set(header) | set(renamed.values())
    return {"added": sorted(set(header) - expected - set(aliases)), "missing": sorted(expected - present),
            "renamed": renamed}


def sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build(con: duckdb.DuckDBPyConnection, files: list[SourceFile], layout: Layout,
          tables: tuple[str, ...]) -> tuple[dict, list[dict]]:
    """Escribe bronze/<tabla>.parquet y bronze/_files.parquet. Devuelve (stats por tabla, registro de archivos)."""
    registry = []
    for f in files:
        diff = header_diff(f.table, f.header)
        registry.append({**f.as_dict(), "header": ",".join(f.header), **{f"header_{k}": v for k, v in diff.items()},
                         "schema_drift": bool(diff["added"] or diff["missing"] or diff["renamed"])})
    reg_df = pl.DataFrame([{**r, "header_added": ",".join(r["header_added"]),
                            "header_missing": ",".join(r["header_missing"]),
                            "header_renamed": ",".join(f"{a}->{c}" for a, c in r["header_renamed"].items())}
                           for r in registry])
    con.register("_reg_df", reg_df)
    con.execute("CREATE OR REPLACE TEMP TABLE _reg AS SELECT * FROM _reg_df")
    con.unregister("_reg_df")
    con.execute(f"COPY _reg TO '{layout.bronze / '_files.parquet'}' (FORMAT parquet)")

    stats = {}
    for t in tables:
        tf = [f for f in files if f.table == t]
        if not tf:
            raise RuntimeError(f"bronze: sin archivos para {t}")
        paths = "[" + ", ".join(sql_str(f.local_path) for f in tf) + "]"
        out = layout.bronze / f"{t}.parquet"
        # Sin ORDER BY: DuckDB conserva el orden de inserción (archivos en orden de clave, filas en orden de archivo).
        con.execute(f"""
            COPY (
                SELECT r.* EXCLUDE (filename), f.key AS _source_key, f.loaded_at::TIMESTAMPTZ AS _loaded_at,
                       try_strptime(regexp_extract(f.key, '_(\\d{{8}})\\.csv$', 1), '%Y%m%d')::DATE AS _partition_date
                FROM read_csv({paths}, all_varchar = true, union_by_name = true, filename = true, header = true,
                              hive_partitioning = false) r
                JOIN _reg f ON r.filename = f.local_path
            ) TO '{out}' (FORMAT parquet, COMPRESSION zstd)""")
        per_file = dict(con.sql(f"SELECT _source_key, count(*) FROM read_parquet('{out}') GROUP BY 1").fetchall())
        for r in registry:
            if r["table"] == t:
                r["n_rows"] = per_file.get(r["key"], 0)
        n_rows = sum(per_file.values())
        stats[t] = {"files": len(tf), "rows": n_rows, "bytes": sum(f.size for f in tf),
                    "header_signatures": len({",".join(f.header) for f in tf}),
                    "files_with_drift": sum(r["schema_drift"] for r in registry if r["table"] == t),
                    "columns": [c[0] for c in con.sql(f"DESCRIBE SELECT * FROM read_parquet('{out}')").fetchall()]}
        log.info("bronze %s: %d archivos, %s filas", t, len(tf), f"{n_rows:,}")
    return stats, registry
