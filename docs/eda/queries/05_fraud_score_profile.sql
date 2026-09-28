-- Respalda: findings.md §5 (distribución de fraud_score según is_fraud).
-- Produce: outputs/tables/05_fraud_score_profile.csv (vía eda/labels.py).
SELECT is_fraud, count(*) AS n, count(fraud_score) AS n_with_score,
       round(quantile_cont(fraud_score, 0.25), 2) AS p25, round(quantile_cont(fraud_score, 0.5), 2) AS p50,
       round(quantile_cont(fraud_score, 0.75), 2) AS p75, round(quantile_cont(fraud_score, 0.95), 2) AS p95,
       round(100.0 * avg((fraud_score >= 80)::INT) FILTER (WHERE fraud_score IS NOT NULL), 2) AS pct_score_ge_80
FROM transactions GROUP BY is_fraud ORDER BY is_fraud
