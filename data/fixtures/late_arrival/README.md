# `late_arrival` fixture (synthetic test data)

> **FIXTURE: no row comes from the LATAM Bank dataset.** IDs carry the prefix `FX-`, names say
> `FIXTURE` and the pipeline marks the source as `fixture` in `manifest.json`. It is generated with
> `python -m data.fixtures.late_arrival.make_fixture` (deterministic) and the CSVs are versioned as is.

## Why it exists
The dataset dictionary announces late arrivals and schema evolution, but they are not in the data: the lag
`process_date − event date` is 0 or −1 and there is a single header signature per table (`docs/eda/data_quality.md`
§B4, §B6). This fixture has the same shape as the bucket (`year=/month=/day=` partitions, BOM, CRLF) and serves to
demonstrate how the pipeline handles a second delivery.

## Deliveries
Each delivery is a folder with S3-style keys; `fixture.json` declares its delivery date (the "load date" used by
the future-dates check). Delivery 2 is overlaid on delivery 1: a repeated key replaces the earlier file, like
a re-delivery that overwrites the object in S3.

| Delivery | File | What it tests |
|---|---|---|
| `delivery_1` | `customers/customers.csv` | FX-CLI-004 with `last_updated` in 2027 (future date) |
| `delivery_1` | `products/products.csv` | FX-PRD-002 opens after FX-TRX-0002; FX-PRD-006 with a future `last_updated` |
| `delivery_1` | `transactions/…/day=15/…` | `Mexico` (FX-TRX-0003), before product opening (0002), `customer_id` that is not the product owner (0005: gold resolves it to the owner), event from 2025-05-31 outside the 12-month window (0015: stays in silver, not in gold) |
| `delivery_1` | `transactions/…/day=16/…` | exact duplicate of FX-TRX-0008, `Mexico` (0007), nonexistent product (0009) |
| `delivery_1` | `complaints/…/day=16/…` | another customer's product (FX-CMP-002), nonexistent product (003), no `category` (004) |
| `delivery_2` | `customers/customers.csv` | snapshot re-delivery: FX-CLI-002 changes segment, new customer FX-CLI-006 |
| `delivery_2` | `transactions/…/day=16/…` | partition re-delivery: without the duplicate and with the missing FX-TRX-0010 |
| `delivery_2` | `transactions/…/day=20/…` | **late arrivals** (events from the 12th, 13th and 14th with a `process_date` of the 20th; correction of 0008 from the 16th) and **schema change**: `transaction_country` arrives as `txn_country` and `merchant_mcc` appears |

Dates fall in May 2026, inside the window of `contracts/gold_contract.md`. The counts the pipeline must produce
for each delivery (including the derived tables and `gold_eval/`) are in `fixture.json` → `expected`. They are
verified by `tests/test_fixture_late_arrival.py` and section 7 of `data/quality_report.md`.

## How to run it
```bash
python -m data.pipeline fixture   # delivery_1 and then delivery_1 + delivery_2 in data/_fixture_run/ (gitignored)
python -m data.pipeline report    # section 7 of the report shows what changed between the two
```
