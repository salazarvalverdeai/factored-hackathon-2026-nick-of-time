-- Respalda: findings.md §5 y expediente W3 (fraud_score como regla determinista de triage de fraude/disputa).
-- Produce: outputs/tables/05_fraud_score_thresholds.csv (vía eda/labels.py). Todas las transacciones (4.4M).
-- Por umbral: transacciones marcadas, fraudes capturados (recall), precisión y marcadas por mes.
WITH t AS (SELECT fraud_score, is_fraud FROM transactions WHERE fraud_score IS NOT NULL),
     tot AS (SELECT count(*) FILTER (WHERE is_fraud) AS n_fraud, count(*) AS n FROM t),
     thr AS (SELECT unnest([30, 50, 60, 70, 80, 90, 95]) AS threshold)
SELECT thr.threshold,
       count(*) FILTER (WHERE t.fraud_score >= thr.threshold) AS n_flagged,
       count(*) FILTER (WHERE t.fraud_score >= thr.threshold AND t.is_fraud) AS n_fraud_flagged,
       any_value(tot.n_fraud) AS n_fraud_total,
       round(100.0 * count(*) FILTER (WHERE t.fraud_score >= thr.threshold AND t.is_fraud) / any_value(tot.n_fraud), 2) AS recall_pct,
       round(100.0 * count(*) FILTER (WHERE t.fraud_score >= thr.threshold AND t.is_fraud)
             / nullif(count(*) FILTER (WHERE t.fraud_score >= thr.threshold), 0), 2) AS precision_pct,
       round(count(*) FILTER (WHERE t.fraud_score >= thr.threshold) / 37.0, 1) AS flagged_per_month
FROM thr CROSS JOIN t CROSS JOIN tot
GROUP BY thr.threshold
ORDER BY thr.threshold
