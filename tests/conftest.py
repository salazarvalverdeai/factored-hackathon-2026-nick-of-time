"""Fixtures de pytest. Todos los tests corren sin red: cualquier conexión de socket desde Python falla."""
from __future__ import annotations

import socket
from datetime import date, datetime

import polars as pl
import pytest

from data.pipeline import contracts


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def guard(*args, **kwargs):
        raise RuntimeError("los tests no deben usar la red")
    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)


def contract_frame(table: str, rows: list[dict], lineage: bool = False) -> pl.DataFrame:
    """DataFrame con todas las columnas del contrato, tipadas; las que no vienen en `rows` quedan nulas.
    Con lineage=True agrega las columnas que silver deja para gold (_loaded_at, _source_key, …)."""
    schema = {c: col.dtype.type for c, col in contracts.SCHEMAS[table].columns.items()}
    df = pl.DataFrame([{c: r.get(c) for c in schema} for r in rows], schema=schema)
    if lineage:
        df = df.with_columns(
            pl.lit(datetime(2026, 6, 17, 23, 0)).dt.replace_time_zone("America/Lima").alias("_loaded_at"),
            pl.lit(f"{table}/test.csv").alias("_source_key"), pl.lit(date(2026, 6, 16)).alias("_partition_date"),
            pl.lit(False).alias("_qc_normalized"))
        if table in contracts.EVENT_DATE:
            df = df.with_columns(pl.lit(0).alias("_lag_days"))
    return df
