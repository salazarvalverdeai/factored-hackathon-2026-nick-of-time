"""Pandera contracts: they accept valid rows and reject invalid ones with the right check."""
from __future__ import annotations

from datetime import date, datetime

import pytest
from pandera.errors import SchemaErrors

from data.pipeline import contracts
from tests.conftest import contract_frame

VALID_TX = {
    "transaction_id": "T1", "transaction_date": datetime(2026, 6, 16, 8, 30), "process_date": date(2026, 6, 16),
    "product_id": "P1", "customer_id": "C1", "transaction_type": "Purchase", "amount": 120.5, "currency": "USD",
    "transaction_country": "México", "transaction_status": "Approved", "response_code": "00", "is_fraud": False,
    "fraud_score": 3.1,
}


def test_valid_rows_pass():
    df = contract_frame("transactions", [VALID_TX, {**VALID_TX, "transaction_id": "T2", "fraud_score": None}])
    contracts.TRANSACTIONS.validate(df, lazy=True)


def test_invalid_rows_fail_with_the_right_checks():
    rows = [
        VALID_TX,
        {**VALID_TX},                                                   # repeated PK
        {**VALID_TX, "transaction_id": "T3", "transaction_country": "Mexico"},  # label not normalized
        {**VALID_TX, "transaction_id": "T4", "fraud_score": 150.0},    # out of range
        {**VALID_TX, "transaction_id": "T5", "amount": None},          # required column null
        {**VALID_TX, "transaction_id": "T6", "transaction_status": "Done"},  # outside the domain
    ]
    with pytest.raises(SchemaErrors) as exc:
        contracts.TRANSACTIONS.validate(contract_frame("transactions", rows), lazy=True)
    fc = exc.value.failure_cases
    failed = {(r["column"], r["check"].split("(")[0]) for r in fc.iter_rows(named=True)}
    assert failed == {("transaction_id", "field_uniqueness"), ("transaction_country", "isin"),
                      ("fraud_score", "in_range"), ("amount", "not_nullable"), ("transaction_status", "isin")}
    assert set(fc["index"].to_list()) == {0, 1, 2, 3, 4, 5}


def test_every_contract_column_maps_to_a_duckdb_type():
    for table in contracts.SCHEMAS:
        assert contracts.PRIMARY_KEY[table] in contracts.required_columns(table)
        for col in contracts.columns(table):
            assert contracts.duckdb_type(table, col) in {"VARCHAR", "DOUBLE", "DATE", "BOOLEAN", "TIMESTAMP"}
