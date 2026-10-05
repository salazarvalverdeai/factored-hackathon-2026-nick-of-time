"""Operational lakehouse (spec 14, ADR 0018): the store's own rows go bronze → silver → gold.

Layers under `data/ops/` (git-ignored):
    bronze/<table>.parquet   faithful copy of the eight §7.1 tables, every value as text, plus `_loaded_at`, `_source`
    silver/<table>.parquet   typed and joined with gold; rows that break a contract go to silver/_quarantine/
The Postgres source (T5) is the same job with another `Snapshot`. `is_fraud`, `gold_eval/` and the bank's score are
never read; demo_transactions (synthetic, ADR 0020) and sessions are never copied.
"""
