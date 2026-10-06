# queries/

## `pitch/`: verification of the pitch numbers
One query per number (or group of numbers) used by the pitch, with its output next to it:

| Query | Output CSV | Numbers |
|---|---|---|
| `p01_w3_share_complaints.sql` | `p01_w3_share_complaints.csv` | 36.4% of complaints are W3; 679 cases/month |
| `p02_fcr_complaint_vs_bank.sql` | `p02_fcr_complaint_vs_bank.csv` | FCR 43.6% vs 76.6% (with Wilson CI95) |
| `p03_complaint_follow_up.sql` | `p03_complaint_follow_up.csv` | 63% require follow-up |
| `p04_complaint_duration_vs_bank.sql` | `p04_complaint_duration_vs_bank.csv` | "AHT 7.2 vs 4.9" (median and mean, both) |
| `p05_complaint_nps_vs_bank.sql` | `p05_complaint_nps_vs_bank.csv` | NPS −85.3 vs −74.5 |
| `p06_w3_resolution_days.sql` | `p06_w3_resolution_days.csv` | p50 resolution of 16 days |
| `p07_fraud_per_month.sql` | `p07_fraud_per_month.csv` | 120 frauds/month |
| `p08_fraud_score_thresholds.sql` | `p08_fraud_score_thresholds.csv` | precision and recall per `fraud_score` threshold |

Copy from the EDA repo (`factored-2026-eda-freddy`, Sep 28, 2026). There, `python -m queries.run` runs all of them against
the EDA views (`scripts/db.py`, Parquet cache of `data/`), rewrites the CSVs, builds `pitch_numbers.csv` (cited vs
recalculated value) and regenerates the table in `docs/eda/README.md`. They cannot be regenerated here: this repo's gold
only has 4 tables and 12 months of transactions, and the numbers come from the full dataset. Each `.sql` says in its header which EDA query and table originally backed the number
(`docs/eda/queries/` → `outputs/tables/`).
The column names and group labels in these `.sql` files and CSVs were translated to English from the EDA repo originals
(`factored-2026-eda-freddy` still uses the Spanish names, e.g. `grupo`, `Todo el banco`).

The EDA queries are in `docs/eda/queries/`, where the documents reference them.

## `ops/`: Bank today and the replay sample for `/analytics` (spec 14 §11)
| Query | Output CSV | What it holds |
|---|---|---|
| `asis_monthly.sql` | `ops/asis_monthly.csv` | W3 complaints per month 2026-01..2026-05: days to first response, escalated, `sla_breached`, resolution days `[data]`; `make ops-replay` runs it on this repo's gold |
| `replay_sample.sql` | none (the replay reads it) | the replay's contacts: a seeded sample of approved card charges per month, sized to the W3 complaints `[data]` |

## `policy/`: sources of `contracts/policies.yaml` values
| Query | Value |
|---|---|
| `implied_usd_rate.sql` | `amount_gate.by_country` `usd_rate` for CO (4,000) and AR (350) `[data]`; runs on this repo's gold, output in the file |

## `eval/`: candidates for the demo and the evaluation cases
| Query | Output CSV | What it holds |
|---|---|---|
| `demo_index.sql` | `eval/demo_index.csv` | approved card transactions per country × zone × split, 2026-03-03 to 2026-05-31 `[data]` (spec 09 §7.2); `python -m eval.demo_index` runs it on this repo's gold |

## `data/`: dataset limits and profile
| Query | Output CSV | What it holds |
|---|---|---|
| `d01_complaint_transaction_link.sql` | `d01_complaint_transaction_link.csv` | whether a disputed-charge (W3) complaint can be linked to a card transaction of the same customer in the 30 days before it, and whether its claimed amount matches one within ±2% `[data]`; shown as the "Dataset limitations" card of `/data` |
| `d02_transactions_per_month.sql` | `d02_transactions_per_month.csv` | transactions per month (2025-06 to 2026-05, the gold window) by product type (debit, credit, other) with the approved, declined, pending and reversed counts and shares `[data]` |
| `d03_customers_transactions_by_country_segment.sql` | `d03_customers_transactions_by_country_segment.csv` | customers and transactions per country (MX, CO, AR) and segment, with country totals `[data]` |
| `d04_fraud_score_distribution.sql` | `d04_fraud_score_distribution.csv` | the bank's `fraud_score` on card transactions per country: share null and counts by band (< 30, 30-49, >= 50); a score, not a label `[data]` |
| `d05_complaints_per_month.sql` | `d05_complaints_per_month.csv` | complaints per month by category, with the W3 share of the month (same W3 rule as `p01`) `[data]` |
| `d06_data_quality_per_table.sql` | `d06_data_quality_per_table.csv` | per gold table: rows, null rate of key columns and rows per `qc_*` flag `[data]` |

`python queries/data/run.py --gold PATH` runs every `queries/data/*.sql` on a gold folder (read-only) and rewrites the CSVs; `python -m data.pipeline report --json` copies each CSV into `data_quality.json` (`complaint_link` for d01, `profile.d02`..`profile.d06` for the rest). The queries are aggregate only (no ids, no personal data) and never read the fraud label or `data/gold_eval/`.
