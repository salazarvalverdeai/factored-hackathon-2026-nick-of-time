-- Pitch number: "120 frauds/month".
-- EDA backing: outputs/tables/04_trigger_events_summary.csv (TRX-01, monthly_mean) and 02_transactions_monthly.csv,
--   via docs/eda/queries/04_trigger_events_monthly.sql and 02_transactions_monthly.sql.
-- Fraud = transactions.is_fraud. Per month: full months 2023-07..2026-05 (35).
SELECT count(*)                                                        AS n_transactions,
       count(*) FILTER (WHERE is_fraud)                                AS n_frauds,
       round(100.0 * count(*) FILTER (WHERE is_fraud) / count(*), 3)   AS pct_fraud,
       count(*) FILTER (WHERE is_fraud AND transaction_date >= TIMESTAMP '2023-07-01'
                        AND transaction_date < TIMESTAMP '2026-06-01') AS n_frauds_full_months,
       35                                                              AS n_full_months,
       round(count(*) FILTER (WHERE is_fraud AND transaction_date >= TIMESTAMP '2023-07-01'
                              AND transaction_date < TIMESTAMP '2026-06-01') / 35.0, 1) AS frauds_per_month,
       count(*) FILTER (WHERE is_fraud AND fraud_score IS NULL)        AS n_frauds_without_score
FROM transactions
