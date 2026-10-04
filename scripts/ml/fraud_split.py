"""Spec 17 T1: time split, split hash and the window-enforcing label reader (AC-01, AC-05, ADR 0022).

Usage (data-like outputs go outside the repo):
    python -m scripts.ml.fraud_split --gold $GOLD --eval $GOLD_EVAL --out /path/outside/repo
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import duckdb
import polars as pl

QUERIES = Path(__file__).resolve().parents[2] / "queries" / "fraud"
TRAIN, VALIDATION, TEST = "train", "validation", "test"
WINDOWS = {  # [start, end) -- mirrors queries/fraud/f02_time_split.sql (a test checks the boundaries)
    TRAIN: ("2025-06-01", "2026-02-01"),
    VALIDATION: ("2026-02-01", "2026-04-01"),
    TEST: ("2026-04-01", "2026-06-01"),
}
LABEL_WINDOWS = frozenset({TRAIN, VALIDATION})  # ADR 0022: test labels are read once, by the evaluation step (17c)


class LabelAccessError(RuntimeError):
    """Raised when the training code asks for labels outside the training/validation windows."""


def connect(gold_dir: str | Path) -> duckdb.DuckDBPyConnection:
    """View over the gold transactions. Labels are exposed only through `read_labels`."""
    con = duckdb.connect()
    path = Path(gold_dir) / "transactions_enriched.parquet"
    con.execute(f"CREATE VIEW transactions_enriched AS SELECT * FROM read_parquet('{path}')")
    return con


def build_split(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    sql = (QUERIES / "f02_time_split.sql").read_text()
    return con.execute(sql).pl().filter(pl.col("split_window").is_not_null())


def split_hash(split: pl.DataFrame) -> str:
    """Deterministic sha256 over the window definitions and the sorted (transaction_id, window) pairs."""
    h = hashlib.sha256(json.dumps(WINDOWS, sort_keys=True).encode())
    for tid, win in split.sort("transaction_id").select("transaction_id", "split_window").iter_rows():
        h.update(f"{tid}|{win}\n".encode())
    return h.hexdigest()


def read_labels(labels_path: str | Path, split: pl.DataFrame, windows) -> pl.DataFrame:
    """Labels for the transactions in `windows` only; any window outside LABEL_WINDOWS raises (AC-05)."""
    windows = set(windows)
    if not windows or not windows <= LABEL_WINDOWS:
        raise LabelAccessError(f"labels may be read only for {sorted(LABEL_WINDOWS)}, asked for {sorted(windows)}")
    ids = split.filter(pl.col("split_window").is_in(sorted(windows))).select("transaction_id", "split_window")
    con = duckdb.connect()
    con.register("ids", ids.to_arrow())
    out = con.execute(
        f"SELECT i.transaction_id, i.split_window, l.is_fraud FROM ids i "
        f"JOIN read_parquet('{labels_path}') l USING (transaction_id)"
    ).pl()
    if not set(out["split_window"].unique().to_list()) <= LABEL_WINDOWS:  # defensive; unreachable by construction
        raise LabelAccessError("test-window labels reached the training code")
    return out


def split_record(split: pl.DataFrame, labels: pl.DataFrame | None = None) -> dict:
    """What later tasks verify: the hash and the counts. The test window is a transaction count only."""
    rec = {"windows": WINDOWS, "split_hash": split_hash(split),
           "n_transactions": dict(split.group_by("split_window").len().iter_rows())}
    if labels is not None:
        rec["n_fraud"] = dict(labels.filter("is_fraud").group_by("split_window").len().iter_rows())
    return rec


def register_labels(con: duckdb.DuckDBPyConnection, labels: pl.DataFrame) -> None:
    """Expose `transaction_labels` from the frame `read_labels` returned, never from the whole label file."""
    con.register("transaction_labels", labels.select("transaction_id", "is_fraud").to_arrow())


def monthly_counts(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Runs f01 (labels joined only before the test window). Needs a `transaction_labels` view on `con`."""
    return con.execute((QUERIES / "f01_monthly_counts.sql").read_text()).pl()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    ap.add_argument("--eval", required=True, help="gold_eval dir (labels; train/validation only are read)")
    ap.add_argument("--out", required=True, help="directory OUTSIDE the repo; data-like outputs go here")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    labels_path = Path(a.eval) / "transaction_labels.parquet"
    con = connect(a.gold)
    split = build_split(con)
    labels = read_labels(labels_path, split, LABEL_WINDOWS)
    rec = split_record(split, labels)
    (out / "split.json").write_text(json.dumps(rec, indent=2))
    register_labels(con, labels)  # the view holds train/validation labels only; f01's CASE is a second guard
    monthly_counts(con).write_csv(out / "monthly_counts.csv")  # f01 never selects test-month labels
    print(json.dumps(rec, indent=2))


if __name__ == "__main__":
    main()
