"""Bronze: faithful copy of the CSVs to Parquet, everything as VARCHAR, with per-row lineage.

Lineage columns: `_source_key` (S3-style key of the file), `_loaded_at` (load date of the file) and
`_partition_date` (date from the name `<table>_YYYYMMDD.csv`; null in dimensions). `union_by_name=true`: a column that
appears only in some files is null in the rest, and bronze keeps it even if the contract does not have it.

For each file the header is compared with the contract: added columns (not in the contract), missing and
renamed (alias declared in contracts.ALIASES).
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
    """Writes bronze/<table>.parquet and bronze/_files.parquet. Returns (stats per table, file registry)."""
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
            raise RuntimeError(f"bronze: no files for {t}")
        paths = "[" + ", ".join(sql_str(f.local_path) for f in tf) + "]"
        out = layout.bronze / f"{t}.parquet"
        # No ORDER BY: DuckDB keeps insertion order (files in key order, rows in file order).
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
        log.info("bronze %s: %d files, %s rows", t, len(tf), f"{n_rows:,}")
    return stats, registry
