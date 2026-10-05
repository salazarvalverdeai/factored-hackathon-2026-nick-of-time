"""Gold loader (spec 03 §7, T2; ADR 0004): card transactions and customer names in one in-memory DuckDB, read-only.

Only two files of `GOLD_PATH` are opened, `transactions_enriched` and `customers`, with named columns: no `is_fraud`
(it lives only in `gold_eval/`, which this loader refuses, constitution #7), and from `customers` only `customer_id`,
`first_name` and `country`, so documents, e-mails, phones and addresses are never loaded (AC-11). Every read names the
session's customer: there is no read of a transaction by id alone, except `owner`, which answers only who owns it so a
cross-customer probe can be logged and answered "not found".
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

import duckdb

from nick_of_time.store import is_demo_run

CARD_TYPES = ("Tarjeta Débito", "Tarjeta Crédito")           # spec 02 §4.3 product mapping: debit, credit
FILES = {"transactions": "transactions_enriched.parquet", "customers": "customers.parquet"}
_LOAD = ("transaction_id, product_id, customer_id, CAST(transaction_date AS DATE) AS transaction_date, amount, currency,"
         " amount_usd, merchant_name AS merchant, transaction_status, fraud_score, product_type, transaction_country")
_TRX = ("transaction_id, product_id, customer_id, transaction_date, amount, currency, amount_usd, merchant,"
        " transaction_status, fraud_score, product_type, transaction_country")   # in GoldTransaction's order


@dataclass(frozen=True)
class GoldTransaction:
    transaction_id: str
    product_id: str
    customer_id: str
    transaction_date: dt.date
    amount: float
    currency: str
    amount_usd: Optional[float]
    merchant: Optional[str]
    transaction_status: str
    fraud_score: Optional[float]
    product_type: str                          # one of CARD_TYPES: the deadline's product (compute_deadline)
    transaction_country: Optional[str]         # where the charge was made: `abroad` (compute_deadline)
    synthetic: bool = False                    # a live demo run's `demo_transactions` row (spec 03 AC-14)


@dataclass(frozen=True)
class GoldCustomer:
    customer_id: str
    first_name: str
    country: str


class Gold:
    """[assumption] memory_limit 512MB and 2 threads keep DuckDB lean on the t3.medium; the table holds ≈ 516k card
    rows sorted by customer_id, so a customer filter prunes row groups without an index (T5 measures AC-13)."""

    def __init__(self, path: Path, *, memory_limit: str = "512MB") -> None:
        path = Path(path).resolve()
        if "gold_eval" in path.parts:                         # constitution #7: the runtime never reads labels
            raise ValueError("the MCP server reads data/gold only, never gold_eval")
        self.path = path                                      # the folder, for the card index (cards.cards_of)
        self._con = duckdb.connect(":memory:", config={"memory_limit": memory_limit, "threads": 2})
        self._con.execute(f"CREATE TABLE card AS SELECT {_LOAD} FROM read_parquet(?) WHERE product_type IN (?, ?) "
                          "AND customer_id IS NOT NULL ORDER BY customer_id",
                          [str(path / FILES["transactions"]), *CARD_TYPES])
        self._con.execute("CREATE TABLE customer AS SELECT customer_id, first_name, country FROM read_parquet(?)",
                          [str(path / FILES["customers"])])

    def _rows(self, sql: str, params: list) -> list[tuple]:
        return self._con.cursor().execute(sql, params).fetchall()        # a cursor per read: safe across threads

    def customer(self, customer_id: str) -> Optional[GoldCustomer]:
        rows = self._rows("SELECT customer_id, first_name, country FROM customer WHERE customer_id = ?", [customer_id])
        return GoldCustomer(*rows[0]) if rows else None

    def transactions(self, customer_id: str, start: dt.date, end: dt.date,
                     statuses: tuple[str, ...]) -> list[GoldTransaction]:
        """The customer's card transactions dated `start..end` (inclusive) with one of `statuses`."""
        marks = ", ".join("?" * len(statuses))
        rows = self._rows(f"SELECT {_TRX} FROM card WHERE customer_id = ? AND transaction_date BETWEEN ? AND ? "
                          f"AND transaction_status IN ({marks})", [customer_id, start, end, *statuses])
        return [GoldTransaction(*row) for row in rows]

    def transaction(self, customer_id: str, transaction_id: str) -> Optional[GoldTransaction]:
        rows = self._rows(f"SELECT {_TRX} FROM card WHERE customer_id = ? AND transaction_id = ?",
                          [customer_id, transaction_id])
        return GoldTransaction(*rows[0]) if rows else None

    def owner(self, transaction_id: str) -> Optional[str]:
        """Only to log a cross-customer probe (policies.yaml scope.cross_customer_request); never returned."""
        rows = self._rows("SELECT customer_id FROM card WHERE transaction_id = ?", [transaction_id])
        return rows[0][0] if rows else None


Synthetic = Callable[[str, str], list[GoldTransaction]]       # (customer_id, demo run_id) -> that run's charges


def synthetic_from(store: Any) -> Synthetic:
    """The store's `demo_transactions` of one demo run as GoldTransaction rows flagged `synthetic` [simulated]."""
    def rows(customer_id: str, run_id: str) -> list[GoldTransaction]:
        return [GoldTransaction(r.transaction_id, r.product_id, r.customer_id, r.transaction_date.date(), r.amount,
                                r.currency, r.amount_usd, r.merchant_name, r.transaction_status, r.fraud_score,
                                r.product_type, r.transaction_country, synthetic=True)
                for r in store.demo_transactions(customer_id, run_id=run_id)]
    return rows


def run_charges(synthetic: Optional[Synthetic], session: Any) -> list[GoldTransaction]:
    """Spec 03 AC-14: the synthetic charges of the session's own run, only for a `live` demo run; none in replay, in
    production or in another run (ADR 0020 rule 2, ADR 0026)."""
    if synthetic is None or session.mode != "live" or not is_demo_run(session.run_id) or not session.customer_id:
        return []
    return synthetic(session.customer_id, session.run_id)


def find(gold: Gold, synthetic: Optional[Synthetic], session: Any, transaction_id: str) -> Optional[GoldTransaction]:
    """The session customer's transaction: gold's, else one of the run's synthetic charges."""
    return gold.transaction(session.customer_id, transaction_id) or next(
        (t for t in run_charges(synthetic, session) if t.transaction_id == transaction_id), None)
