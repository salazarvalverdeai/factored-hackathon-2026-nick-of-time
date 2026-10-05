"""Gold card products and card-transaction countries (spec 03 §7, T4 and T5; ADR 0004), in-memory DuckDB, read-only.

From `products` only the card rows and five columns are loaded: `product_id`, `customer_id`, the type (debit or credit),
the **last 4** digits of `product_number` (the full number is never loaded, AC-11) and `product_status`. From
`transactions_enriched` only `transaction_id`, `customer_id` and `transaction_country` of card transactions, so
`open_case` can tell an operation abroad (spec 03 §6 `compute_deadline`). Every read names the session's customer,
except `owner`, which answers only who owns a product so a cross-customer probe can be logged (D-052).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import duckdb

from mcp_server.gold import CARD_TYPES, FILES

PRODUCTS = "products.parquet"
_CARD = "product_id, customer_id, type, last4, status"


@dataclass(frozen=True)
class GoldCard:
    product_id: str
    customer_id: str
    type: str                     # debit | credit
    last4: str
    status: str                   # gold product_status: Active | Blocked | Closed | Suspended


class GoldCards:
    """[assumption] A card without four trailing digits is not loaded: no tool can name it (≈ 140k card rows, none
    such in gold v1 [data]: `data/gold/products.parquet`, 2026-10-05)."""

    def __init__(self, path: Path, *, memory_limit: str = "256MB") -> None:
        path = Path(path).resolve()
        if "gold_eval" in path.parts:                         # constitution #7
            raise ValueError("the MCP server reads data/gold only, never gold_eval")
        self._con = duckdb.connect(":memory:", config={"memory_limit": memory_limit, "threads": 2})
        debit, credit = CARD_TYPES
        self._con.execute(
            "CREATE TABLE card AS SELECT product_id, customer_id, CASE product_type WHEN ? THEN 'debit' ELSE 'credit' "
            "END AS type, right(product_number, 4) AS last4, product_status AS status FROM read_parquet(?) "
            "WHERE product_type IN (?, ?) AND customer_id IS NOT NULL AND regexp_full_match(right(product_number, 4), "
            "'[0-9]{4}') ORDER BY customer_id, product_id", [debit, str(path / PRODUCTS), debit, credit])
        self._con.execute(
            "CREATE TABLE trx_country AS SELECT transaction_id, customer_id, transaction_country FROM read_parquet(?) "
            "WHERE product_type IN (?, ?) AND customer_id IS NOT NULL ORDER BY customer_id",
            [str(path / FILES["transactions"]), debit, credit])

    def _rows(self, sql: str, params: list) -> list[tuple]:
        return self._con.cursor().execute(sql, params).fetchall()       # a cursor per read: safe across threads

    def card(self, customer_id: str, product_id: str) -> Optional[GoldCard]:
        rows = self._rows(f"SELECT {_CARD} FROM card WHERE customer_id = ? AND product_id = ?", [customer_id, product_id])
        return GoldCard(*rows[0]) if rows else None

    def cards(self, customer_id: str) -> list[GoldCard]:
        return [GoldCard(*row) for row in self._rows(f"SELECT {_CARD} FROM card WHERE customer_id = ? ORDER BY "
                                                     "product_id", [customer_id])]

    def owner(self, product_id: str) -> Optional[str]:
        """Only to log a cross-customer probe (policies.yaml scope.cross_customer_request); never returned."""
        rows = self._rows("SELECT customer_id FROM card WHERE product_id = ?", [product_id])
        return rows[0][0] if rows else None

    def transaction_country(self, customer_id: str, transaction_id: str) -> Optional[str]:
        rows = self._rows("SELECT transaction_country FROM trx_country WHERE customer_id = ? AND transaction_id = ?",
                          [customer_id, transaction_id])
        return rows[0][0] if rows else None


@lru_cache(maxsize=2)
def _loaded(path: str) -> GoldCards:
    return GoldCards(Path(path))


def shared_cards() -> GoldCards:
    """The one `GoldCards` of the process, over `GOLD_PATH` (the entry point's gold, spec 03 T8), loaded on first use
    and shared by the tool modules: their factories take only the entry point's dependencies [assumption]."""
    path = os.environ.get("GOLD_PATH", "").strip()
    if not path:
        raise RuntimeError("GOLD_PATH is not set: no gold cards to read")
    return _loaded(str(Path(path).resolve()))
