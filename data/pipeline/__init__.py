"""Pipeline bronze → silver → gold del dataset LATAM Bank (tablas de la idea W3: customers, products, transactions,
complaints).

    python -m data.pipeline run --source s3        # bronze desde S3 (credenciales de .env), silver, gold
    python -m data.pipeline run --source local     # mismo flujo sobre el espejo local data/<tabla>/ (sin red)
    python -m data.pipeline fixture                # fixture etiquetado de llegadas tardías y cambio de schema
    python -m data.pipeline report                 # data/quality_report.md desde los resultados de las corridas

Capas (bajo el directorio de trabajo, `data/` por defecto):
    bronze/<tabla>.parquet   copia fiel del CSV (todo VARCHAR) + linaje (_source_key, _loaded_at, _partition_date)
    silver/<tabla>.parquet   tipado según el contrato (contracts.py), renombres declarados, normalización de
                             etiquetas, dedup/upsert por PK y validación pandera; filas que violan el contrato van a
                             silver/_quarantine/<tabla>.parquet
    gold/<tabla>.parquet     según contracts/gold_contract.md: silver + flags de calidad (qc_*), transactions en la
                             ventana de 12 meses con customer_id resuelto por join y sin is_fraud, más customer_profile
                             y transactions_enriched; gold/manifest.json (versión, fecha, filas, sha256 de cada tabla);
                             gold/run_results.json con todos los conteos del reporte
    gold_eval/<tabla>.parquet  transaction_labels (transaction_id, is_fraud): solo para evaluación
"""
