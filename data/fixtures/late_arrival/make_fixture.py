"""Generates the `late_arrival` fixture: two synthetic deliveries with the same shape as the S3 bucket.

    python -m data.fixtures.late_arrival.make_fixture

FIXTURE: no row comes from the LATAM Bank dataset. IDs carry the prefix `FX-` and names say FIXTURE. Each row
has a purpose (comment) and the counts the pipeline must produce are in fixture.json → expected.

Dates fall in May 2026, inside the 12-month window of contracts/gold_contract.md (R1).

- delivery_1 (2026-05-17): dimensions + transactions from May 15 and 16 + complaints from May 16. Includes an exact
  duplicate, `Mexico` labels, a transaction before product opening, an FK to another customer's product, orphan FKs,
  future dates, a complaint without `category` (violates the contract) and an event from 2025-05-31 (outside the
  window: does not reach gold).
- delivery_2 (2026-05-21): re-delivery of the customers snapshot (1 change, 1 new customer), re-delivery of the May
  16 partition (without the duplicate, with a row that was missing) and a new May 20 partition with **late arrivals**
  (events from May 12 to 16) and a **schema change** (`transaction_country` → `txn_country`, new column `merchant_mcc`).
Files are written with BOM and CRLF, like the ones in the bucket.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

HERE = Path(__file__).resolve().parent

CUSTOMER_COLS = ["customer_id", "document_number", "document_type", "first_name", "last_name", "date_of_birth",
                 "gender", "email", "mobile_phone", "landline_phone", "address", "city", "state", "country",
                 "postal_code", "detected_accent", "segment", "credit_score", "estimated_monthly_income", "occupation",
                 "marital_status", "education_level", "registration_date", "registration_branch_id",
                 "customer_status", "last_updated", "accepts_marketing"]
PRODUCT_COLS = ["product_id", "customer_id", "product_type", "product_number", "currency", "current_balance",
                "credit_limit", "interest_rate", "opening_date", "expiration_date", "opening_branch_id",
                "product_status", "opening_channel", "has_linked_app", "days_past_due", "last_transaction_date",
                "last_updated"]
TX_COLS = ["transaction_id", "transaction_date", "process_date", "product_id", "customer_id", "transaction_type",
           "transaction_category", "amount", "currency", "amount_usd", "channel", "branch_id", "merchant_name",
           "merchant_category", "transaction_country", "transaction_city", "transaction_status", "response_code",
           "is_fraud", "fraud_score", "latitude", "longitude"]
# Producer schema v2: transaction_country renamed and new merchant_mcc at the end
TX_COLS_V2 = [("txn_country" if c == "transaction_country" else c) for c in TX_COLS] + ["merchant_mcc"]
COMPLAINT_COLS = ["complaint_id", "creation_date", "process_date", "customer_id", "case_type", "category",
                  "subcategory", "reception_channel", "affected_product_id", "related_branch_id",
                  "origin_interaction_id", "description", "claimed_amount", "currency", "priority", "status",
                  "assigned_agent_id", "assignment_date", "first_response_date", "resolution_date", "closing_date",
                  "sla_breached", "resolution_days", "resolution", "compensation_granted", "resolution_satisfaction",
                  "is_repeat_complainer"]


def customer(cid, country, segment, last_updated, registration="2020-01-15 10:00:00", **kw) -> dict:
    return {"customer_id": cid, "document_number": f"FX{cid[-3:]}0000", "document_type": "Pasaporte",
            "first_name": "FIXTURE", "last_name": f"Cliente {cid[-3:]}", "gender": "O", "country": country,
            "segment": segment, "registration_date": registration, "customer_status": "Active",
            "last_updated": last_updated, "accepts_marketing": "False", **kw}


def product(pid, cid, ptype, currency, opening, last_updated="2026-05-10 08:00:00", **kw) -> dict:
    return {"product_id": pid, "customer_id": cid, "product_type": ptype, "product_number": f"FX-{pid[-3:]}",
            "currency": currency, "current_balance": "1000.00", "opening_date": opening, "product_status": "Active",
            "opening_channel": "App", "has_linked_app": "True", "last_updated": last_updated, **kw}


def tx(tid, ts, process, pid, cid, ttype, amount, currency, country, status="Approved", **kw) -> dict:
    return {"transaction_id": tid, "transaction_date": ts, "process_date": process, "product_id": pid,
            "customer_id": cid, "transaction_type": ttype, "amount": amount, "currency": currency, "channel": "POS",
            "transaction_country": country, "transaction_status": status, "response_code": "00",
            "is_fraud": "False", "fraud_score": "3.10", **kw}


def complaint(kid, ts, cid, case_type, category, product=None, **kw) -> dict:
    return {"complaint_id": kid, "creation_date": ts, "process_date": ts[:10], "customer_id": cid,
            "case_type": case_type, "category": category, "reception_channel": "Call Center",
            "affected_product_id": product, "description": f"FIXTURE: queja de {category or 'sin categoría'}",
            "priority": "Medium", "status": "Open", "sla_breached": "False", "is_repeat_complainer": "False", **kw}


CUSTOMERS_D1 = [
    customer("FX-CLI-001", "México", "Basic", "2026-05-01 09:00:00", credit_score="700.0"),
    customer("FX-CLI-002", "México", "Basic", "2026-04-20 12:00:00"),
    customer("FX-CLI-003", "Colombia", "Plus", "2026-04-02 15:30:00"),
    customer("FX-CLI-004", "Argentina", "Premium", "2027-01-15 08:00:00"),       # future date (FUT-01)
    customer("FX-CLI-005", "Colombia", "Student", "2026-03-11 11:11:00"),
]
CUSTOMERS_D2 = [
    *[c for c in CUSTOMERS_D1 if c["customer_id"] != "FX-CLI-002"],
    customer("FX-CLI-002", "México", "Plus", "2026-05-19 10:00:00"),            # segment change (update)
    customer("FX-CLI-006", "México", "Basic", "2026-05-18 17:00:00",            # new customer (insert)
             registration="2026-05-18 17:00:00"),
]
PRODUCTS_D1 = [
    product("FX-PRD-001", "FX-CLI-001", "Tarjeta Crédito", "USD", "2024-01-10", credit_limit="5000.00"),
    product("FX-PRD-002", "FX-CLI-001", "Cuenta Ahorro", "USD", "2026-05-16"),   # opens after FX-TRX-0002
    product("FX-PRD-003", "FX-CLI-002", "Tarjeta Débito", "USD", "2025-03-01"),
    product("FX-PRD-004", "FX-CLI-003", "Cuenta Corriente", "COP", "2023-05-05"),
    product("FX-PRD-005", "FX-CLI-004", "Tarjeta Crédito", "ARS", "2022-11-11", credit_limit="900000.00"),
    product("FX-PRD-006", "FX-CLI-005", "Préstamo Personal", "COP", "2025-08-20",
            last_updated="2026-12-31 00:00:00"),                                 # future date (FUT-02)
]
TX_15 = [
    tx("FX-TRX-0001", "2026-05-15 09:10:00", "2026-05-15", "FX-PRD-001", "FX-CLI-001", "Purchase", "120.50", "USD",
       "México", transaction_category="Food", merchant_name="FIXTURE Tienda", merchant_category="Food"),
    tx("FX-TRX-0002", "2026-05-15 10:00:00", "2026-05-15", "FX-PRD-002", "FX-CLI-001", "Deposit", "500.00", "USD",
       "México", channel="Branch"),                                              # before product opening (ORD-01)
    tx("FX-TRX-0003", "2026-05-15 11:30:00", "2026-05-15", "FX-PRD-003", "FX-CLI-002", "Withdrawal", "80.00", "USD",
       "Mexico", channel="ATM"),                                                 # Mexico label (LBL-01)
    tx("FX-TRX-0004", "2026-05-15 12:00:00", "2026-05-15", "FX-PRD-004", "FX-CLI-003", "Transfer", "250000.00",
       "COP", "Colombia", amount_usd="60.00", channel="App"),
    tx("FX-TRX-0005", "2026-05-15 13:45:00", "2026-05-15", "FX-PRD-001", "FX-CLI-005", "Purchase", "35.00", "USD",
       "México"),                                                                # another customer's product (OWN-01)
    tx("FX-TRX-0015", "2025-05-31 22:00:00", "2026-05-15", "FX-PRD-001", "FX-CLI-001", "Purchase", "15.00", "USD",
       "México"),                                                                # outside the window (WIN-01)
]
TX_16_BASE = [
    tx("FX-TRX-0006", "2026-05-16 08:30:00", "2026-05-16", "FX-PRD-005", "FX-CLI-004", "Purchase", "999.99", "ARS",
       "Argentina", amount_usd="1.10", channel="Web", is_fraud="True", fraud_score="87.50"),
    tx("FX-TRX-0007", "2026-05-16 09:00:00", "2026-05-16", "FX-PRD-003", "FX-CLI-002", "Payment", "45.00", "USD",
       "Mexico", channel="App"),                                                 # Mexico label (LBL-01)
    tx("FX-TRX-0008", "2026-05-16 10:15:00", "2026-05-16", "FX-PRD-004", "FX-CLI-003", "Purchase", "150000.00", "COP",
       "Colombia", status="Pending"),                                            # corrected in delivery_2
    tx("FX-TRX-0009", "2026-05-16 11:00:00", "2026-05-16", "FX-PRD-999", "FX-CLI-001", "Purchase", "20.00", "USD",
       "México"),                                                                # nonexistent product (FK-03)
]
TX_16_D1 = [*TX_16_BASE, dict(TX_16_BASE[2])]                                    # exact duplicate of 0008 (DUP-01)
TX_16_D2 = [*TX_16_BASE,                                                         # re-delivery: without the duplicate
            tx("FX-TRX-0010", "2026-05-16 16:20:00", "2026-05-16", "FX-PRD-003", "FX-CLI-002", "Purchase", "12.00",
               "USD", "México")]                                                 # row that was missing (insert)
TX_20_V2 = [
    {**TX_16_BASE[2], "process_date": "2026-05-20", "transaction_status": "Approved"},  # correction of 0008 (DUP-02)
    tx("FX-TRX-0011", "2026-05-12 14:00:00", "2026-05-20", "FX-PRD-001", "FX-CLI-001", "Purchase", "60.00", "USD",
       "México"),                                                                # arrives 8 days late
    tx("FX-TRX-0012", "2026-05-13 18:30:00", "2026-05-20", "FX-PRD-004", "FX-CLI-003", "Withdrawal", "100000.00",
       "COP", "Colombia", channel="ATM"),                                        # arrives 7 days late
    tx("FX-TRX-0013", "2026-05-14 07:45:00", "2026-05-20", "FX-PRD-005", "FX-CLI-004", "Purchase", "5000.00", "ARS",
       "Argentina", is_fraud="True", fraud_score="55.00"),                       # arrives 6 days late
    tx("FX-TRX-0014", "2026-05-20 09:00:00", "2026-05-20", "FX-PRD-003", "FX-CLI-002", "Purchase", "25.00", "USD",
       "Mexico"),                                                                # on time; Mexico via the renamed column
]
for i, row in enumerate(TX_20_V2):
    row["txn_country"] = row.pop("transaction_country")
    row["merchant_mcc"] = ["5411", "5999", "6011", "5812", "5411"][i]
COMPLAINTS_D1 = [
    complaint("FX-CMP-001", "2026-05-16 09:00:00", "FX-CLI-001", "Claim", "Transactions", "FX-PRD-001",
              subcategory="Cargo no reconocido", priority="High"),
    complaint("FX-CMP-002", "2026-05-16 10:00:00", "FX-CLI-002", "Complaint", "Fees", "FX-PRD-004",
              subcategory="Cobro indebido"),                                     # another customer's product (OWN-02)
    complaint("FX-CMP-003", "2026-05-16 11:00:00", "FX-CLI-003", "Request", "Transactions", "FX-PRD-777"),  # FK-05
    complaint("FX-CMP-004", "2026-05-16 12:00:00", "FX-CLI-005", "Complaint", None),  # no category: contract
    complaint("FX-CMP-005", "2026-05-16 13:00:00", "FX-CLI-004", "Suggestion", "Service"),
]

DELIVERIES = {
    "delivery_1": {
        "customers/customers.csv": (CUSTOMER_COLS, CUSTOMERS_D1),
        "products/products.csv": (PRODUCT_COLS, PRODUCTS_D1),
        "transactions/year=2026/month=05/day=15/transactions_20260515.csv": (TX_COLS, TX_15),
        "transactions/year=2026/month=05/day=16/transactions_20260516.csv": (TX_COLS, TX_16_D1),
        "complaints/year=2026/month=05/day=16/complaints_20260516.csv": (COMPLAINT_COLS, COMPLAINTS_D1),
    },
    "delivery_2": {
        "customers/customers.csv": (CUSTOMER_COLS, CUSTOMERS_D2),
        "transactions/year=2026/month=05/day=16/transactions_20260516.csv": (TX_COLS, TX_16_D2),
        "transactions/year=2026/month=05/day=20/transactions_20260520.csv": (TX_COLS_V2, TX_20_V2),
    },
}


def write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\r\n", extrasaction="raise")
    w.writeheader()
    w.writerows([{c: r.get(c) for c in cols} for r in rows])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"))


def main() -> None:
    for delivery, files in DELIVERIES.items():
        for key, (cols, rows) in files.items():
            write_csv(HERE / delivery / key, cols, rows)
            print(f"{delivery}/{key}: {len(rows)} rows")


if __name__ == "__main__":
    main()
