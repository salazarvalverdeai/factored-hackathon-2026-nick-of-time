"""Spec 09 AC-02: the demo customers must have recent charges, or the demo never reaches a case in replay mode.

One rule per scenario (`eval/demo/customers.json`), checked on gold with replay today (DEMO_TODAY, ADR 0020):
  * "Unrecognized charge on one card": the customer's card charges in the search window hold exactly one charge, on a
    card of the stated product (debit or credit).
  * "Unrecognized charge among several recent ones": the window holds charges of at least 2 different cards.
The window is the one `search_transaction` uses without a date (`apps/mcp/mcp_server/reads.py`: NO_DATE_DAYS = 30 days
back from today, statuses Approved and Pending, cards only). Reads gold products and transactions only, never gold_eval.

    python -m scripts.demo_customers                          # check the six demo customers against gold
    python -m scripts.demo_customers --pick CO credit Basic   # lowest dev customer id meeting the one-card rule
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Optional

import polars as pl

from eval import demo_index

ROOT = Path(__file__).resolve().parents[1]
CUSTOMERS = ROOT / "eval/demo/customers.json"
DEMO_TODAY = dt.date(2026, 6, 1)                       # ADR 0020 replay date
WINDOW_DAYS = 30                                       # reads.NO_DATE_DAYS
STATUSES = ("Approved", "Pending")                     # reads.STATUSES
CARDS = {"Tarjeta Débito": "debit", "Tarjeta Crédito": "credit"}
COUNTRY = {"MX": "México", "CO": "Colombia", "AR": "Argentina"}
ONE_CARD, SEVERAL = "one_card", "several"


def gold_dir() -> Optional[Path]:
    """The gold folder holding the parquet files, or None when this checkout has no gold."""
    folder = ROOT / "data/gold"
    return folder if (folder / "transactions.parquet").exists() and (folder / "products.parquet").exists() else None


def rule_of(customer: dict) -> tuple[str, Optional[str]]:
    """(rule, product) from the scenario text and the product named in display_name, e.g. "(MX · debit)"."""
    rule = SEVERAL if "several" in customer["scenario"] else ONE_CARD
    found = re.search(r"\b(debit|credit)\b", customer["display_name"])
    return rule, found.group(1) if found else None


def charges(folder: Path, customer_ids: Optional[list[str]] = None, today: dt.date = DEMO_TODAY) -> pl.DataFrame:
    """Card charges of the search window: customer_id, product_id, product (debit|credit), date."""
    cards = (pl.scan_parquet(folder / "products.parquet").filter(pl.col("product_type").is_in(list(CARDS)))
             .select("product_id", pl.col("product_type").replace_strict(CARDS).alias("product")))
    lazy = (pl.scan_parquet(folder / "transactions.parquet")
            .filter(pl.col("transaction_status").is_in(list(STATUSES)))
            .with_columns(pl.col("transaction_date").cast(pl.Date).alias("date"))
            .filter((pl.col("date") >= today - dt.timedelta(days=WINDOW_DAYS)) & (pl.col("date") <= today)))
    if customer_ids is not None:
        lazy = lazy.filter(pl.col("customer_id").is_in(customer_ids))
    return lazy.join(cards, on="product_id").select("customer_id", "product_id", "product", "date").collect()


def holds(rule: str, product: Optional[str], rows: pl.DataFrame) -> bool:
    """Does one customer's window (`rows`) meet the rule?"""
    if rule == SEVERAL:
        return rows["product_id"].n_unique() >= 2
    return rows.height == 1 and (product is None or rows["product"][0] == product)


def check(folder: Path, customers: list[dict]) -> dict[str, bool]:
    rows = charges(folder, [c["customer_id"] for c in customers])
    out = {}
    for c in customers:
        rule, product = rule_of(c)
        out[c["customer_id"]] = holds(rule, product, rows.filter(pl.col("customer_id") == c["customer_id"]))
    return out


def pick(folder: Path, country: str, product: str, segment: str, exclude: frozenset[str] = frozenset()) -> Optional[str]:
    """Deterministic: the lowest customer_id of the dev split and the demo index, with the country and segment, meeting the one-card rule."""
    people = (pl.scan_parquet(folder / "customers.parquet").filter(
        (pl.col("country") == COUNTRY[country]) & (pl.col("segment") == segment)).select("customer_id").collect())
    indexed = {row["customer_id"] for row in demo_index.read()}      # reference.json needs a row of the demo index
    ids = [i for i in people["customer_id"] if i in indexed and demo_index.customer_split(i) == "dev"
           and i not in exclude]
    rows = charges(folder, ids)
    for i in sorted(ids):
        if holds(ONE_CARD, product, rows.filter(pl.col("customer_id") == i)):
            return i
    return None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--gold", type=Path, default=None, help="gold folder (default data/gold)")
    parser.add_argument("--pick", nargs=3, metavar=("COUNTRY", "PRODUCT", "SEGMENT"))
    args = parser.parse_args(argv)
    folder = args.gold or gold_dir()
    if folder is None:
        print("no gold found", file=sys.stderr)
        return 2
    customers = json.loads(CUSTOMERS.read_text(encoding="utf-8"))
    if args.pick:
        country, product, segment = args.pick
        print(pick(folder, country, product, segment, frozenset(c["customer_id"] for c in customers)))
        return 0
    results = check(folder, customers)
    for c in customers:
        print(f"{'PASS' if results[c['customer_id']] else 'FAIL'}  {c['customer_id']}  {rule_of(c)}  {c['display_name']}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
