"""Read-only gold lookups the api needs and the store does not hold (spec 05): the demo customers, a case's
transaction and the customer's products. Gold is read-only at runtime (ADR 0004); the api never writes it.

`Catalog` is the seam: `FixtureCatalog` serves the simulated demo customers of `app.fixtures` [simulated]; the gold
Parquet reader implements the same protocol when the data pipeline publishes its accessors (follow-up of spec 05).
A lookup that finds nothing returns None and the api answers UNAVAILABLE: it never invents a transaction.
"""
from __future__ import annotations

from typing import Any, Optional, Protocol

from app import fixtures as fx


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
