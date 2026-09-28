-- Número del pitch: "36.4% de complaints" y "679 casos/mes" de cargos no reconocidos y cobros indebidos (W3).
-- Respaldo EDA: outputs/tables/03_coverage_summary.csv (pct_W3_disputas) y 04_workflow_scorecard.csv
--   (W3_disputas, volumen_mensual_complaints), vía docs/eda/queries/03_apply_mapping.sql y 04_complaints_base.sql.
-- W3 = reglas CMP-01..03 v1 de docs/eda/queries/03_workflow_mapping.csv:
--   CMP-01 category = 'Transactions' AND case_type = 'Claim'
--   CMP-02 category = 'Transactions' AND case_type IN ('Complaint', 'Request')
--   CMP-03 category = 'Fees' AND case_type IN ('Claim', 'Complaint')
-- Denominador del %: todos los complaints (toda la ventana). Por mes: meses completos 2023-07..2026-05 (35).
WITH c AS (
    SELECT strftime(creation_date, '%Y-%m') AS ym,
           (category = 'Transactions' AND case_type IN ('Claim', 'Complaint', 'Request'))
           OR (category = 'Fees' AND case_type IN ('Claim', 'Complaint')) AS is_w3
    FROM complaints
)
SELECT count(*)                                                        AS n_complaints,
       count(*) FILTER (WHERE is_w3)                                   AS n_w3,
       round(100.0 * count(*) FILTER (WHERE is_w3) / count(*), 3)      AS pct_w3,
       count(*) FILTER (WHERE is_w3 AND ym BETWEEN '2023-07' AND '2026-05') AS n_w3_full_months,
       35                                                              AS n_full_months,
       round(count(*) FILTER (WHERE is_w3 AND ym BETWEEN '2023-07' AND '2026-05') / 35.0, 1) AS w3_per_month
FROM c
