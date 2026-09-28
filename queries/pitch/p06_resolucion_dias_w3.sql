-- Número del pitch: "resolución de complaints p50 16 días (igual en todo el banco)".
-- Respaldo EDA: outputs/tables/04_workflow_scorecard.csv (W3_disputas y TODOS, métrica resolucion_dias_p50), vía
--   docs/eda/queries/04_complaints_base.sql + eda/outcomes.py. W3 = reglas CMP-01..03 v1 (ver p01).
-- Denominador: complaints con resolution_days no nulo (resueltos/cerrados), toda la ventana.
WITH c AS (
    SELECT resolution_days, status,
           (category = 'Transactions' AND case_type IN ('Claim', 'Complaint', 'Request'))
           OR (category = 'Fees' AND case_type IN ('Claim', 'Complaint')) AS is_w3
    FROM complaints
), g AS (
    SELECT 'W3 (CMP-01..03)' AS grupo, * FROM c WHERE is_w3
    UNION ALL
    SELECT 'Todo el banco', * FROM c
)
SELECT grupo,
       count(*)                                         AS n_complaints,
       count(resolution_days)                           AS n_con_resolucion,
       round(quantile_cont(resolution_days, 0.5), 1)    AS resolucion_dias_p50,
       round(quantile_cont(resolution_days, 0.95), 1)   AS resolucion_dias_p95,
       round(100.0 * count(*) FILTER (WHERE status IN ('Resolved', 'Closed')) / count(*), 3) AS pct_resueltos_cerrados
FROM g
GROUP BY grupo
ORDER BY grupo
