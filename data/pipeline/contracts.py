"""Contratos de schema (pandera sobre polars) de las tablas silver.

Cada contrato fija columnas, tipos, nulabilidad, unicidad de la PK y dominios. Los dominios salen de los valores
observados en el EDA (`outputs/tables/00_enum_values.csv`, `01_range_checks.csv`); donde el diccionario documenta un
valor que no aparece (CURP, MXN) se admite igual. Las columnas nullable=False son las obligatorias de
`outputs/tables/01_null_rates.csv` (required = True).

Además del schema, el contrato declara:
- PRIMARY_KEY: clave para dedup/upsert (gana la versión con process_date más reciente, luego la carga más reciente).
- EVENT_DATE: fecha del evento en las tablas de hechos (rezago = process_date − fecha del evento).
- ALIASES: renombres de columnas aceptados (evolución de schema declarada por el productor): alias → canónico.
- NORMALIZE: etiquetas que se corrigen en silver (valor crudo → valor canónico), contadas antes de corregir.
"""
from __future__ import annotations

import polars as pl
import pandera.polars as pa

CONTRACT_VERSION = "v1"

COUNTRIES = ["México", "Colombia", "Argentina"]
CURRENCIES = ["USD", "COP", "ARS", "MXN"]
PRODUCT_TYPES = ["Cuenta Ahorro", "Tarjeta Crédito", "Cuenta Corriente", "Tarjeta Débito", "Préstamo Personal",
                 "Préstamo Hipotecario", "Inversión", "Seguro"]
MERCHANT_CATEGORIES = ["Food", "Services", "Other", "Transport", "Entertainment", "Health"]

TS = pl.Datetime("us")


def _col(dtype, *checks: pa.Check, required: bool = False, unique: bool = False) -> pa.Column:
    return pa.Column(dtype, list(checks), nullable=not required, unique=unique)


def _isin(values: list[str]) -> pa.Check:
    return pa.Check.isin(values)


CUSTOMERS = pa.DataFrameSchema({
    "customer_id": _col(pl.Utf8, required=True, unique=True),
    "document_number": _col(pl.Utf8, required=True),
    "document_type": _col(pl.Utf8, _isin(["DNI", "CE", "Pasaporte", "CC", "CURP"]), required=True),
    "first_name": _col(pl.Utf8),
    "last_name": _col(pl.Utf8),
    "date_of_birth": _col(pl.Date),
    "gender": _col(pl.Utf8, _isin(["F", "M", "O"])),
    "email": _col(pl.Utf8),
    "mobile_phone": _col(pl.Utf8),
    "landline_phone": _col(pl.Utf8),
    "address": _col(pl.Utf8),
    "city": _col(pl.Utf8),
    "state": _col(pl.Utf8),
    "country": _col(pl.Utf8, _isin(COUNTRIES), required=True),
    "postal_code": _col(pl.Utf8),
    "detected_accent": _col(pl.Utf8, _isin(["mexican", "colombian", "argentine"])),
    "segment": _col(pl.Utf8, _isin(["Basic", "Plus", "Premium", "Student"]), required=True),
    "credit_score": _col(pl.Float64, pa.Check.in_range(300, 850)),
    "estimated_monthly_income": _col(pl.Float64, pa.Check.ge(0)),
    "occupation": _col(pl.Utf8),
    "marital_status": _col(pl.Utf8, _isin(["Married", "Divorced", "Single", "Widowed"])),
    "education_level": _col(pl.Utf8, _isin(["College Prep", "High School", "University", "Graduate", "Elementary"])),
    "registration_date": _col(TS, required=True),
    "registration_branch_id": _col(pl.Utf8),
    "customer_status": _col(pl.Utf8, _isin(["Active", "Inactive", "Suspended", "Closed"]), required=True),
    "last_updated": _col(TS),
    "accepts_marketing": _col(pl.Boolean),
}, name="customers")

PRODUCTS = pa.DataFrameSchema({
    "product_id": _col(pl.Utf8, required=True, unique=True),
    "customer_id": _col(pl.Utf8, required=True),
    "product_type": _col(pl.Utf8, _isin(PRODUCT_TYPES), required=True),
    "product_number": _col(pl.Utf8),
    "currency": _col(pl.Utf8, _isin(CURRENCIES), required=True),
    "current_balance": _col(pl.Float64),
    "credit_limit": _col(pl.Float64, pa.Check.ge(0)),
    "interest_rate": _col(pl.Float64, pa.Check.ge(0)),
    "opening_date": _col(pl.Date, required=True),
    "expiration_date": _col(pl.Date),
    "opening_branch_id": _col(pl.Utf8),
    "product_status": _col(pl.Utf8, _isin(["Active", "Closed", "Blocked", "Suspended"]), required=True),
    "opening_channel": _col(pl.Utf8, _isin(["Branch", "Web", "App", "Call Center"])),
    "has_linked_app": _col(pl.Boolean),
    "days_past_due": _col(pl.Float64, pa.Check.ge(0)),
    "last_transaction_date": _col(TS),
    "last_updated": _col(TS),
}, name="products")

TRANSACTIONS = pa.DataFrameSchema({
    "transaction_id": _col(pl.Utf8, required=True, unique=True),
    "transaction_date": _col(TS, required=True),
    "process_date": _col(pl.Date, required=True),
    "product_id": _col(pl.Utf8, required=True),
    "customer_id": _col(pl.Utf8, required=True),
    "transaction_type": _col(pl.Utf8, _isin(["Purchase", "Withdrawal", "Transfer", "Payment", "Deposit",
                                             "Adjustment"]), required=True),
    "transaction_category": _col(pl.Utf8, _isin(MERCHANT_CATEGORIES)),
    "amount": _col(pl.Float64, pa.Check.gt(0), required=True),
    "currency": _col(pl.Utf8, _isin(CURRENCIES), required=True),
    "amount_usd": _col(pl.Float64, pa.Check.ge(0)),
    "channel": _col(pl.Utf8, _isin(["POS", "ATM", "Web", "App", "Branch", "Transfer"])),
    "branch_id": _col(pl.Utf8),
    "merchant_name": _col(pl.Utf8),
    "merchant_category": _col(pl.Utf8, _isin(MERCHANT_CATEGORIES)),
    "transaction_country": _col(pl.Utf8, _isin(COUNTRIES + ["USA", "Spain", "Brazil"])),
    "transaction_city": _col(pl.Utf8),
    "transaction_status": _col(pl.Utf8, _isin(["Approved", "Declined", "Pending", "Reversed"]), required=True),
    "response_code": _col(pl.Utf8, _isin(["00", "05", "14", "51", "54"])),
    "is_fraud": _col(pl.Boolean),
    "fraud_score": _col(pl.Float64, pa.Check.in_range(0, 100)),
    "latitude": _col(pl.Float64, pa.Check.in_range(-90, 90)),
    "longitude": _col(pl.Float64, pa.Check.in_range(-180, 180)),
}, name="transactions")

COMPLAINTS = pa.DataFrameSchema({
    "complaint_id": _col(pl.Utf8, required=True, unique=True),
    "creation_date": _col(TS, required=True),
    "process_date": _col(pl.Date, required=True),
    "customer_id": _col(pl.Utf8, required=True),
    "case_type": _col(pl.Utf8, _isin(["Complaint", "Claim", "Request", "Suggestion"]), required=True),
    "category": _col(pl.Utf8, _isin(["Transactions", "Fees", "Technical", "Branch", "Service"]), required=True),
    "subcategory": _col(pl.Utf8, _isin(["Cargo no reconocido", "Cobro indebido", "Problema con app",
                                        "Atención en sucursal", "Calidad de servicio"])),
    "reception_channel": _col(pl.Utf8, _isin(["Call Center", "Email", "Web", "App", "Branch", "Regulator"])),
    "affected_product_id": _col(pl.Utf8),
    "related_branch_id": _col(pl.Utf8),
    "origin_interaction_id": _col(pl.Utf8),
    "description": _col(pl.Utf8),
    "claimed_amount": _col(pl.Float64, pa.Check.ge(0)),
    "currency": _col(pl.Utf8, _isin(CURRENCIES)),
    "priority": _col(pl.Utf8, _isin(["Low", "Medium", "High", "Critical"]), required=True),
    "status": _col(pl.Utf8, _isin(["Open", "In Process", "Escalated", "Resolved", "Closed", "Rejected"]),
                   required=True),
    "assigned_agent_id": _col(pl.Utf8),
    "assignment_date": _col(TS),
    "first_response_date": _col(TS),
    "resolution_date": _col(TS),
    "closing_date": _col(TS),
    "sla_breached": _col(pl.Boolean),
    "resolution_days": _col(pl.Float64, pa.Check.ge(0)),
    "resolution": _col(pl.Utf8),
    "compensation_granted": _col(pl.Float64, pa.Check.ge(0)),
    "resolution_satisfaction": _col(pl.Float64, pa.Check.in_range(1, 5)),
    "is_repeat_complainer": _col(pl.Boolean),
}, name="complaints")

SCHEMAS: dict[str, pa.DataFrameSchema] = {
    "customers": CUSTOMERS, "products": PRODUCTS, "transactions": TRANSACTIONS, "complaints": COMPLAINTS,
}
PRIMARY_KEY = {"customers": "customer_id", "products": "product_id", "transactions": "transaction_id",
               "complaints": "complaint_id"}
EVENT_DATE = {"transactions": "transaction_date", "complaints": "creation_date"}
# Evolución de schema declarada: el productor anunció que `transaction_country` puede llegar como `txn_country`.
ALIASES: dict[str, dict[str, str]] = {"transactions": {"txn_country": "transaction_country"}}
NORMALIZE: dict[str, dict[str, dict[str, str]]] = {
    "customers": {"country": {"Mexico": "México"}},
    "transactions": {"transaction_country": {"Mexico": "México"}},
}

_DUCKDB_TYPES = {pl.Utf8: "VARCHAR", pl.Float64: "DOUBLE", pl.Date: "DATE", pl.Boolean: "BOOLEAN", TS: "TIMESTAMP",
                 pl.Int64: "BIGINT"}


def columns(table: str) -> list[str]:
    return list(SCHEMAS[table].columns)


def required_columns(table: str) -> list[str]:
    return [c for c, col in SCHEMAS[table].columns.items() if not col.nullable]


def duckdb_type(table: str, column: str) -> str:
    """Tipo DuckDB al que se castea la columna en silver (derivado del dtype del contrato)."""
    dtype = SCHEMAS[table].columns[column].dtype.type
    for pl_type, db_type in _DUCKDB_TYPES.items():
        if dtype == pl_type:
            return db_type
    raise TypeError(f"{table}.{column}: dtype {dtype} sin tipo DuckDB")
