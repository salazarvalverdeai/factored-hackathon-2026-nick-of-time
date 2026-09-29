"""Bronze → silver → gold pipeline for the LATAM Bank dataset (tables for the W3 idea: customers, products,
transactions, complaints).

    python -m data.pipeline run --source s3        # bronze from S3 (credentials from .env), silver, gold
    python -m data.pipeline run --source local     # same flow over the local mirror data/<table>/ (no network)
    python -m data.pipeline fixture                # labeled fixture of late arrivals and schema change
    python -m data.pipeline report                 # data/quality_report.md from the run results

Layers (under the working directory, `data/` by default):
    bronze/<table>.parquet   faithful copy of the CSV (all VARCHAR) + lineage (_source_key, _loaded_at, _partition_date)
    silver/<table>.parquet   typed per the contract (contracts.py), declared renames, label normalization,
                             dedup/upsert by PK and pandera validation; rows that violate the contract go to
                             silver/_quarantine/<table>.parquet
    gold/<table>.parquet     per contracts/gold_contract.md: silver + quality flags (qc_*), transactions in the
                             12-month window with customer_id resolved by join and without is_fraud, plus
                             customer_profile and transactions_enriched; gold/manifest.json (version, date, rows,
                             sha256 of each table); gold/run_results.json with all the report counts
    gold_eval/<table>.parquet  transaction_labels (transaction_id, is_fraud): for evaluation only
"""
