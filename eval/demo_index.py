"""Demo index (spec 09 T1): runs queries/eval/demo_index.sql on gold and writes eval/demo_index.csv.

Usage, from the repo root after `make setup`: python -m eval.demo_index
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Optional

import duckdb

ROOT = Path(__file__).resolve().parents[1]
QUERY = ROOT / "queries/eval/demo_index.sql"
INDEX = ROOT / "eval/demo_index.csv"
SPLITS = {7: "dev", 8: "heldout", 9: "heldout"}       # contracts/policies.yaml data_splits.by_customer; 0-6 is train


def customer_split(customer_id: str) -> str:
    """Spec 09 §7.1: the first 8 hex digits of md5(customer_id), as an integer, mod 10. Stable across engines."""
    return SPLITS.get(int(hashlib.md5(customer_id.encode()).hexdigest()[:8], 16) % 10, "train")


def build(root: Path = ROOT) -> tuple[list[str], list[tuple]]:
    """Columns and rows of the index, reading `root`/data/gold/."""
    query = QUERY.read_text(encoding="utf-8").replace("'data/gold/", f"'{root.as_posix()}/data/gold/")
    con = duckdb.connect()
    try:
        cursor = con.execute(query)
        return [column[0] for column in cursor.description], cursor.fetchall()
    finally:
        con.close()


def write(path: Path = INDEX, root: Path = ROOT) -> int:
    columns, rows = build(root)
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(["" if value is None else value for value in row] for row in rows)
    return len(rows)


def read(path: Path = INDEX) -> list[dict[str, Optional[str]]]:
    """The committed index, one dict per row; an empty cell (no merchant, no score) is None."""
    with path.open(encoding="utf-8", newline="") as source:
        return [{key: value or None for key, value in row.items()} for row in csv.DictReader(source)]


if __name__ == "__main__":
    print(f"{INDEX.relative_to(ROOT).as_posix()}: {write()} candidates")
