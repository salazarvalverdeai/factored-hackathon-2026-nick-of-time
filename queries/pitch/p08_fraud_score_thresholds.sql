-- Pitch number: precision/recall per fraud_score threshold (">= 50: precision 100%, recall 48.8%";
--   ">= 30: precision 79.6%"; "45/month").
-- EDA backing: outputs/tables/05_fraud_score_thresholds.csv, via docs/eda/queries/05_fraud_score_thresholds.sql.
-- Exact replica of that query (recall over frauds WITH a score; flagged/month = total / 37) plus two extra columns so
-- the pitch does not mix up denominators:
--   recall_all_frauds_pct: recall over ALL frauds, including those without a score (20.6%).
--   flagged_per_month_35: flagged in full months 2023-07..2026-05 / 35 (same base as "120 frauds/month").
WITH t AS (SELECT fraud_score, is_fraud,
                  transaction_date >= TIMESTAMP '2023-07-01' AND transaction_date < TIMESTAMP '2026-06-01' AS full_month
           FROM transactions),
     tot AS (SELECT count(*) FILTER (WHERE is_fraud AND fraud_score IS NOT NULL) AS n_fraud_scored,
                    count(*) FILTER (WHERE is_fraud) AS n_fraud_all
             FROM t),
     thr AS (SELECT unnest([30, 50, 60, 70, 80, 90, 95]) AS threshold)
SELECT thr.threshold,
       count(*) FILTER (WHERE t.fraud_score >= thr.threshold)                    AS n_flagged,
       count(*) FILTER (WHERE t.fraud_score >= thr.threshold AND t.is_fraud)     AS n_frauds_flagged,
       any_value(tot.n_fraud_scored)                                             AS n_frauds_with_score,
       any_value(tot.n_fraud_all)                                                AS n_frauds_all,
       round(100.0 * count(*) FILTER (WHERE t.fraud_score >= thr.threshold AND t.is_fraud)
             / nullif(count(*) FILTER (WHERE t.fraud_score >= thr.threshold), 0), 2) AS precision_pct,
       round(100.0 * count(*) FILTER (WHERE t.fraud_score >= thr.threshold AND t.is_fraud)
             / any_value(tot.n_fraud_scored), 2)                                 AS recall_with_score_pct,
       round(100.0 * count(*) FILTER (WHERE t.fraud_score >= thr.threshold AND t.is_fraud)
             / any_value(tot.n_fraud_all), 2)                                    AS recall_all_frauds_pct,
       round(count(*) FILTER (WHERE t.fraud_score >= thr.threshold) / 37.0, 1)   AS flagged_per_month_37,
       round(count(*) FILTER (WHERE t.fraud_score >= thr.threshold AND t.full_month) / 35.0, 1) AS flagged_per_month_35
FROM thr CROSS JOIN t CROSS JOIN tot
GROUP BY thr.threshold
ORDER BY thr.threshold
