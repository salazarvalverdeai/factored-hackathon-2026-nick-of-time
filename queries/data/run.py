"""Runs every queries/data/*.sql on a gold folder (read-only) and writes its output next to it as CSV [data].

    python queries/data/run.py [--gold data/gold]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, default=HERE.parents[1] / "data" / "gold")
    gold = parser.parse_args().gold.resolve()
    con = duckdb.connect()
    for table in ("complaints", "transactions", "products"):
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{gold / table}.parquet')")
    for sql in sorted(HERE.glob("*.sql")):
        frame = con.sql(sql.read_text(encoding="utf-8")).pl()
        frame = frame.with_columns((100 * frame["numerator"] / frame["denominator"]).round(1).alias("pct"))
        frame.write_csv(sql.with_suffix(".csv"))
        print(sql.name, frame, sep="\n")


if __name__ == "__main__":
    main()
