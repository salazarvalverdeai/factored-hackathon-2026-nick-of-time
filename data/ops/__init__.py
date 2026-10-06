"""Operational lakehouse (spec 14, ADR 0018): the store's own rows go bronze → silver → gold.

    python -m data.ops run --source sample      # a seeded in-memory store over gold (T1–T4, offline)
    python -m data.ops replay                   # §11: Bank today and real card charges replayed through S0 (T8)

Layers under `data/ops/` (git-ignored):
    bronze/<table>.parquet   faithful copy of the eight §7.1 tables, every value as text, plus `_loaded_at`, `_source`
    silver/<table>.parquet   typed and joined with gold; rows that break a contract go to silver/_quarantine/
    gold/ops_kpis.parquet, gold/feedback_cases.parquet, manifest.json, ops_kpis.json (export, spec 14 §7.4)
The Postgres source (T5, `make ops-live`) is the same job with another `Snapshot` (`bronze.from_postgres`), layers
in data/ops/live/, and changes only the Live series of the committed export. `is_fraud`, `gold_eval/` and the bank's score are
never read; demo_transactions (synthetic, ADR 0020) and sessions are never copied.
"""
