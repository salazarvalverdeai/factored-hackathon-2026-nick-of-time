# Gold contract — what the agent reads and what it doesn't

> For David (pipeline). The agent does not read bronze or silver: only `gold/`. Everything here is consumed by the
> tools through the session's `customer_id`, with DuckDB over Parquet. The "pre-digested" part is the derived tables in
> section 3 and the fixtures in section 4. Version with `manifest.json`.

## 0. General rules
- Format: Parquet, one folder per table in `data/gold/<table>/`, partitioned only where stated.
- Keys: `customer_id`, `product_id`, `transaction_id`, `case_id` are strings; they are never rewritten.
- Dates in UTC as `TIMESTAMP`; the "operating day" is resolved in the agent, not in gold.
- Countries normalized: `MX`, `CO`, `AR` (`México`/`Mexico` is fixed in silver).
- **`is_fraud` goes into no table the tools read.** It lives only in `gold_eval/` (section 5). If the agent
  could read it, the evaluation would be leakage and the block would "guess" the label.
- No credential data, and no dictionary columns that aren't used (less is more).
- `manifest.json`: version, date, rows per table, hash per file, date range, checks applied with counts.

## 0b. Partitions (once, in gold; everything else hangs from here)
- `customers.split` = `hash(customer_id) mod 10` → `train` (0–6), `dev` (7), `heldout` (8–9). It propagates to
  `products`, `transactions`, `demo_customers`, `demo_transactions` and `demo_index.csv`.
- `transactions.period` = `fit` (2025-06-01 to 2026-02-28) or `measure` (2026-03-01 to 2026-05-31).
- Rules: development cases use only `dev` customers; the agent's held-out uses only `heldout`; the fraud
  model and the zone calibration are fitted on `train` × `fit` and measured on `heldout` × `measure`.
- Rule G6 (in addition to G1–G5): `gold_eval/` is read only by the harness; no tool and not the agent have a path to it.

## 1. Base tables the tools read

| Table | Grain | Columns | Who uses it |
|---|---|---|---|
| `customers` | 1 row per customer | `customer_id`, `country`, `segment`, `customer_status`, `document_type`, `document_last4` (last 4 only, for the mock OTP), `preferred_language` (derived: `es`; `pt` only in fixtures) | mock identity; regulatory clock (country) |
| `products` | 1 row per product | `product_id`, `customer_id`, `product_type` (Débito, Crédito, …), `product_status` (Active/Blocked/Closed/Suspended), `opening_date`, `currency`, `credit_limit` | `search_transaction` (ownership), `block_card`, `get_product_status` |
| `transactions` | 1 row per transaction; partition `year/month` | `transaction_id`, `product_id`, `customer_id` (**resolved by join**, don't trust the raw one), `ts`, `amount`, `currency`, `amount_usd`, `merchant`, `channel`, `transaction_type`, `transaction_status` (Approved/Declined/Pending/Reversed), `response_code`, `fraud_score` (0–100 or NULL) | `search_transaction`, `get_fraud_score` (provider `dataset`) |
| `exchange_rates` | 1 row per day and pair | `date`, `source_currency`, `target_currency`, `rate` | show amounts in USD if needed; optional |

Checks that must have passed before writing gold (the counts go to the manifest): duplicates removed;
`transactions.product_id` exists in `products`; `products.customer_id` exists in `customers`; `ts` not in the future;
`ts >= products.opening_date` (rows that fail are flagged `flag_before_opening=true`, not deleted);
`fraud_score` between 0 and 100 or NULL.

## 2. Mutable state (does NOT go in gold)
`product_status` changes when the agent blocks. Gold is read-only: the block is written to the agent's state
table (`case_events` / `product_state` in DynamoDB or SQLite), and `get_product_status()` reads the mutable state
**first** and the gold **second**. David doesn't have to do anything here; it's just so it's clear.

## 3. Derived tables ("the pre-digested part") that do go in gold

| Table | Grain | Columns | What for |
|---|---|---|---|
| `customer_profile` | 1 row per customer | `customer_id`, `country`, `segment`, `n_products_active`, `n_tx_90d`, `avg_amount_usd_90d`, `p95_amount_usd_90d`, `top_merchants_90d` (list of 5), `usual_channels` (list), `n_reversed_90d`, `n_declined_90d`, `last_tx_ts` | score provider `rules` (amount vs usual, known merchant); context for the copilot; segment for metrics |
| `transactions_enriched` | 1 row per transaction from the **last 12 months** (3 years not needed) | all of `transactions` + `amount_vs_p95` (ratio), `is_known_merchant` (bool), `hour_local`, `is_weekend`, `country_mismatch` (bool, if the merchant/channel suggests another country), `days_since_opening`, `same_merchant_count_7d`, `flag_before_opening` | `search_transaction` returns this; features for the `rules` provider and for plan B `model` |
| `product_state_snapshot` | 1 row per product | `product_id`, `product_status`, `snapshot_ts` | starting point for the mutable state; the agent copies it at startup |

## 4. Fixtures for demo and evaluation (curated, go in gold)

| Table | What it is | How it's built |
|---|---|---|
| `demo_customers` | 30–50 real customers from the dataset picked by hand: 3 countries × 4 segments, with at least 3 products and recent activity; column `demo_language` (`es` or `pt` assigned by us, labeled as team-generated) | filter + sampling with a fixed seed |
| `demo_transactions` | For each demo customer, their transactions from the last 90 days **plus** a set marked by zone: `expected_zone` (`high` ≥ 50, `medium` 30–49, `human` < 30 or NULL), `scenario` (normal, ambiguous with 3 candidates, high amount, no score, reversed) | selection with a fixed seed; nothing invented: they are real transactions from the dataset |
| `demo_index.csv` | Readable table: `customer_id`, country, segment, language, `split` (dev or heldout), `transaction_id`, amount, date, score, expected zone, scenario | Data 2 writes the messages for the eval cases from this table |

## 5. Evaluation and analytics only (outside the tools' reach)

| Folder | Contents | Who reads it |
|---|---|---|
| `gold_eval/transaction_labels` | `transaction_id`, `is_fraud`, `fraud_score` | only the harness (zone calibration, plan B) |
| `gold_analytics/` | `complaints` (with category and rules CMP-01/02/03 applied), `interactions` (reason, FCR, follow-up, duration), `surveys` (joined by `interaction_id`), `kpis_pitch.csv` (the pitch numbers already computed) | `/analytics`, `/data`, slides |

## 6. Freshness and the updates fixture
- `data/fixtures/late_arrival/`: two `transactions` partitions that "arrive late" and a file with a
  new column (`merchant_category`). The pipeline processes them in a second run; manifest v2 shows the
  delta (new rows, new column, checks re-run). Labeled as a fixture in the README.
- The agent states in `/data` which manifest version it is using.

## 7. Minimum deliveries per day
- **Tue 29:** `customers`, `products`, `transactions` (12 months) in gold with `split` and `period` + manifest v1 + `make setup`. With this
  the agent already runs EV-0001.
- **Wed 30:** `customer_profile`, `transactions_enriched`, `product_state_snapshot`, `demo_*`.
- **Thu 1:** `gold_eval/`, `gold_analytics/`, late arrival fixture, manifest v2.
