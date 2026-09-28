-- Número del pitch: precisión/recall por umbral de fraud_score (">= 50: precisión 100%, recall 48.8%";
--   ">= 30: precisión 79.6%"; "45/mes").
-- Respaldo EDA: outputs/tables/05_fraud_score_thresholds.csv, vía docs/eda/queries/05_fraud_score_thresholds.sql.
-- Réplica exacta de esa query (recall sobre fraudes CON score; marcadas/mes = total / 37) y dos columnas extra para
-- que el pitch no confunda denominadores:
--   recall_todos_fraudes_pct: recall sobre TODOS los fraudes, incluidos los que no tienen score (20.6%).
--   marcadas_por_mes_35: marcadas en meses completos 2023-07..2026-05 / 35 (misma base que "120 fraudes/mes").
WITH t AS (SELECT fraud_score, is_fraud,
                  transaction_date >= TIMESTAMP '2023-07-01' AND transaction_date < TIMESTAMP '2026-06-01' AS full_month
           FROM transactions),
     tot AS (SELECT count(*) FILTER (WHERE is_fraud AND fraud_score IS NOT NULL) AS n_fraud_scored,
                    count(*) FILTER (WHERE is_fraud) AS n_fraud_all
             FROM t),
     thr AS (SELECT unnest([30, 50, 60, 70, 80, 90, 95]) AS threshold)
SELECT thr.threshold,
       count(*) FILTER (WHERE t.fraud_score >= thr.threshold)                    AS n_marcadas,
       count(*) FILTER (WHERE t.fraud_score >= thr.threshold AND t.is_fraud)     AS n_fraudes_marcados,
       any_value(tot.n_fraud_scored)                                             AS n_fraudes_con_score,
       any_value(tot.n_fraud_all)                                                AS n_fraudes_todos,
       round(100.0 * count(*) FILTER (WHERE t.fraud_score >= thr.threshold AND t.is_fraud)
             / nullif(count(*) FILTER (WHERE t.fraud_score >= thr.threshold), 0), 2) AS precision_pct,
       round(100.0 * count(*) FILTER (WHERE t.fraud_score >= thr.threshold AND t.is_fraud)
             / any_value(tot.n_fraud_scored), 2)                                 AS recall_con_score_pct,
       round(100.0 * count(*) FILTER (WHERE t.fraud_score >= thr.threshold AND t.is_fraud)
             / any_value(tot.n_fraud_all), 2)                                    AS recall_todos_fraudes_pct,
       round(count(*) FILTER (WHERE t.fraud_score >= thr.threshold) / 37.0, 1)   AS marcadas_por_mes_37,
       round(count(*) FILTER (WHERE t.fraud_score >= thr.threshold AND t.full_month) / 35.0, 1) AS marcadas_por_mes_35
FROM thr CROSS JOIN t CROSS JOIN tot
GROUP BY thr.threshold
ORDER BY thr.threshold
