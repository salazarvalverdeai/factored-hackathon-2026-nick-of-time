# Gold contract — LATAM Bank (v1)

> Written on Sep 28 2026 from the team's 4 requirements (R1–R4). Anything that doesn't follow from those 4 points is
> marked **[proposal]** and can be changed by bumping the contract version. It is applied by `data/pipeline/gold.py`; the
> rules G1–G5 are checked on every run (if one fails, gold is not published) and in `tests/`.

## Requirements
| # | Requirement | How it's met |
|---|---|---|
| R1 | 12 months of transactions | Window = last 12 full months: `2025-06-01 00:00 ≤ transaction_date < 2026-06-01 00:00` (same full-month convention as the EDA) |
| R2 | `customer_id` resolved by join | In gold, `transactions.customer_id` = the `products.customer_id` of the `product_id` (the product's owner), not the file's `customer_id` |
| R3 | `is_fraud` only in `gold_eval/` | No table in `data/gold/` has `is_fraud` or columns derived from it; the label lives in `data/gold_eval/transaction_labels` |
| R4 | Derived tables | `customer_profile` and `transactions_enriched` in `data/gold/` |

## Location and access
- `data/gold/`: `customers`, `products`, `transactions`, `complaints`, `customer_profile`, `transactions_enriched`
  (Parquet) and `manifest.json`. It is the only thing the solution reads (agent, tools, service).
- `data/gold_eval/`: `transaction_labels` (Parquet). Only the evaluation reads it, joining on `transaction_id`.
- The manifest (`data/gold/manifest.json`) lists both folders with rows and sha256.

## Tables

### `transactions` (R1, R2, R3)
- Rows: silver transactions with `transaction_date` in the R1 window.
- `customer_id`: the product's owner, by join with `products`. **[proposal]** If the `product_id` does not exist in
  `products`, `customer_id` is left null and `qc_product_orphan = true`: the row is kept but is never attributed to the
  file's `customer_id`.
- `_customer_id_source`: the `customer_id` that came in the file (lineage, to audit `qc_product_other_customer`).
- No `is_fraud`. `fraud_score` does stay **[proposal]**: it is the triage signal for the W3 idea (Slack questions 5 and 7
  pending: whether it is a real-time input or an evaluation variable).
- `qc_*` flags as in the rest of gold.

### `transactions_enriched` (R4) **[proposed columns]**
One row per transaction in `gold.transactions`: its content columns (no `_*` lineage, no `is_fraud`) plus
`product_type`, `product_status`, `product_opening_date` (from `products`) and `customer_country`, `customer_segment` (from the
resolved `customer_id`). Known limitation: customers and products are a single snapshot at the cut, so a segment
change rewrites that customer's historical rows (`data_quality.md` §A1, leakage risk).

### `customer_profile` (R4) **[proposed columns]**
One row per customer in `gold.customers`:
`customer_id`, `country`, `segment`, `customer_status`, `registration_date`, `n_products`, `n_active_products`,
`n_transactions_12m`, `n_declined_12m`, `n_reversed_12m`, `first_transaction_at_12m`, `last_transaction_at_12m`,
`n_complaints_12m` (complaints with `creation_date` in the R1 window) and `qc_future_last_updated`.
No personal data (name, document, email, phone numbers and address stay only in `gold.customers`) and no `is_fraud`
or aggregates of it.

### `customers`, `products`, `complaints`
Silver + `qc_*` flags, complete (no window) **[proposal]**. In `complaints`, `customer_id` is the case's: it is not
resolved through the product because `affected_product_id` belongs to another customer in 100% of cases
(`data_quality.md` §B3).

### `gold_eval/transaction_labels` (R3)
`transaction_id`, `is_fraud` for exactly the transactions in `gold.transactions`.

## Verifiable rules (every run)
| Rule | Condition |
|---|---|
| G1 | No table in `data/gold/` has the `is_fraud` column |
| G2 | `min` and `max` of `gold.transactions.transaction_date` within the R1 window |
| G3 | 0 rows in `gold.transactions` with an existing product and `customer_id` ≠ `products.customer_id` |
| G4 | `transaction_labels` and `gold.transactions` have the same set of `transaction_id` (1:1) |
| G5 | `customer_profile` has one row per customer in `gold.customers` and `transactions_enriched` one per transaction in `gold.transactions` |

## Versioning
Contract v1. A change of columns or window is v2: this file is updated, along with `CONTRACT_VERSION` in
`data/pipeline/contracts.py`, and the manifest records the new version.
