"""Read-only gold lookups the api needs and the store does not hold (spec 05): the demo customers, a case's
transaction and the customer's products. Gold is read-only at runtime (ADR 0004); the api never writes it.

`Catalog` is the seam: `GoldCatalog` reads `GOLD_PATH` (production, spec 05 Task 7) and the demo customers of spec 09
(`eval/demo/customers.json`); `FixtureCatalog` serves the simulated customers of `app.fixtures` [simulated] to the
tests and the stub. A lookup that finds nothing returns None and the api answers UNAVAILABLE: it never invents data.
"""
from __future__ import annotations

import json
import os
import threading
import unicodedata
from pathlib import Path
from typing import Any, Optional, Protocol

from app import fixtures as fx

DEMO_CUSTOMERS = Path(__file__).resolve().parents[3] / "eval/demo/customers.json"   # /srv/eval/... in the image
DEMO_KEYS = ("customer_id", "display_name", "country", "segment", "scenario", "language")   # spec 01 §6.2, no score
CARD_TYPES = ("Tarjeta Débito", "Tarjeta Crédito")           # spec 02 §4.3 product mapping, as apps/mcp gold.py
# gold customers.country, folded -> ISO code, as apps/mcp reads.py COUNTRY
COUNTRY = {"mexico": "MX", "argentina": "AR", "colombia": "CO", "brasil": "BR", "brazil": "BR", "peru": "PE",
           "chile": "CL"}


def _code(country: Optional[str]) -> Optional[str]:
    plain = "".join(c for c in unicodedata.normalize("NFD", (country or "").lower()) if unicodedata.category(c) != "Mn")
    return COUNTRY.get(plain.strip())


class Catalog(Protocol):
    def customers(self) -> list[dict[str, Any]]:
        """`{customer_id, display_name, country, segment, scenario, language}` of the demo customers."""

    def customer(self, customer_id: str) -> Optional[dict[str, Any]]: ...

    def transaction(self, transaction_id: str) -> Optional[dict[str, Any]]:
        """`{transaction_id, amount, currency, date, merchant, synthetic}` as `CaseTransaction`."""

    def products(self, customer_id: str) -> list[dict[str, Any]]:
        """`{product_id, type, last4, status}` of the customer's cards (gold status, before any override)."""


class FixtureCatalog:
    def customers(self) -> list[dict[str, Any]]:
        return [dict(c) for c in fx.CUSTOMERS]

    def customer(self, customer_id: str) -> Optional[dict[str, Any]]:
        return next((dict(c) for c in fx.CUSTOMERS if c["customer_id"] == customer_id), None)

    def transaction(self, transaction_id: str) -> Optional[dict[str, Any]]:
        if transaction_id != fx.TRANSACTION_ID:
            return None
        return {"transaction_id": fx.TRANSACTION_ID, "amount": 1250.0, "currency": "USD", "date": "2026-05-31",
                "merchant": "TIENDA X", "synthetic": False}

    def products(self, customer_id: str) -> list[dict[str, Any]]:
        if customer_id != fx.OWNER:
            return []
        return [{"product_id": fx.PRODUCT_ID, "type": "debit", "last4": "4417", "status": "Active"}]


class GoldCatalog:
    """Gold Parquet read in place by DuckDB, one query per lookup with named columns only (no `is_fraud`, no documents,
    no full card number) [assumption: ≈ 10-50 ms per lookup on gold v1, measured locally 2026-10-05]. A session may be
    opened only for a spec 09 demo customer that gold also holds, so the MCP server finds the same customer (D-052)."""

    def __init__(self, path: Path | str, *, demo: Path = DEMO_CUSTOMERS, memory_limit: str = "256MB") -> None:
        import duckdb                                              # only the gold image needs it

        path = Path(path).resolve()
        if "gold_eval" in str(path):                               # constitution #7: the runtime never reads labels
            raise ValueError("the api reads data/gold only, never gold_eval")
        self._files = {k: str(path / f"{k}.parquet") for k in ("customers", "products", "transactions_enriched")}
        self._demo = [{k: c[k] for k in DEMO_KEYS} for c in json.loads(Path(demo).read_text())]
        self._con = duckdb.connect(":memory:", config={"memory_limit": memory_limit, "threads": 2})
        self._lock = threading.Lock()

    def _rows(self, sql: str, params: list) -> list[tuple]:
        with self._lock:
            cursor = self._con.cursor()
        return cursor.execute(sql, params).fetchall()               # a cursor per read: safe across threads

    def customers(self) -> list[dict[str, Any]]:
        return [dict(c) for c in self._demo]

    def customer(self, customer_id: str) -> Optional[dict[str, Any]]:
        demo = next((c for c in self._demo if c["customer_id"] == customer_id), None)
        if demo is None:
            return None
        rows = self._rows("SELECT country FROM read_parquet(?) WHERE customer_id = ?",
                          [self._files["customers"], customer_id])
        if not rows or _code(rows[0][0]) != demo["country"]:
            return None                                            # not in gold, or another country: fail closed
        return dict(demo)

    def transaction(self, transaction_id: str) -> Optional[dict[str, Any]]:
        rows = self._rows("SELECT transaction_id, amount, currency, CAST(transaction_date AS DATE), merchant_name "
                          "FROM read_parquet(?) WHERE transaction_id = ? AND product_type IN (?, ?)",
                          [self._files["transactions_enriched"], transaction_id, *CARD_TYPES])
        if not rows:
            return None
        tid, amount, currency, date, merchant = rows[0]
        return {"transaction_id": tid, "amount": float(amount), "currency": currency, "date": date.isoformat(),
                "merchant": merchant, "synthetic": False}

    def products(self, customer_id: str) -> list[dict[str, Any]]:
        debit = CARD_TYPES[0]
        rows = self._rows("SELECT product_id, CASE product_type WHEN ? THEN 'debit' ELSE 'credit' END, "
                          "right(product_number, 4), product_status FROM read_parquet(?) WHERE customer_id = ? "
                          "AND product_type IN (?, ?) AND regexp_full_match(right(product_number, 4), '[0-9]{4}') "
                          "ORDER BY product_id", [debit, self._files["products"], customer_id, *CARD_TYPES])
        return [{"product_id": p, "type": t, "last4": last4, "status": status} for p, t, last4, status in rows]


def catalog_from_env() -> Catalog:
    """GoldCatalog when GOLD_PATH is set (prod mounts /gold/v1 read-only, infra/compose.yml), else the fixtures."""
    gold = os.getenv("GOLD_PATH")
    return GoldCatalog(gold) if gold else FixtureCatalog()
