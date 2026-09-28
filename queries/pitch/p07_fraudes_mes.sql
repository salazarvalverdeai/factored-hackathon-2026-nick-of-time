-- Número del pitch: "120 fraudes/mes".
-- Respaldo EDA: outputs/tables/04_trigger_events_summary.csv (TRX-01, monthly_mean) y 02_transactions_monthly.csv,
--   vía docs/eda/queries/04_trigger_events_monthly.sql y 02_transactions_monthly.sql.
-- Fraude = transactions.is_fraud. Por mes: meses completos 2023-07..2026-05 (35).
SELECT count(*)                                                        AS n_transacciones,
       count(*) FILTER (WHERE is_fraud)                                AS n_fraudes,
       round(100.0 * count(*) FILTER (WHERE is_fraud) / count(*), 3)   AS pct_fraude,
       count(*) FILTER (WHERE is_fraud AND transaction_date >= TIMESTAMP '2023-07-01'
                        AND transaction_date < TIMESTAMP '2026-06-01') AS n_fraudes_meses_completos,
       35                                                              AS n_meses_completos,
       round(count(*) FILTER (WHERE is_fraud AND transaction_date >= TIMESTAMP '2023-07-01'
                              AND transaction_date < TIMESTAMP '2026-06-01') / 35.0, 1) AS fraudes_por_mes,
       count(*) FILTER (WHERE is_fraud AND fraud_score IS NULL)        AS n_fraudes_sin_score
FROM transactions
