-- Pitch number: "complaint resolution p50 16 days (the same across the whole bank)".
-- EDA backing: outputs/tables/04_workflow_scorecard.csv (W3_disputes and ALL, metric resolucion_dias_p50), via
--   docs/eda/queries/04_complaints_base.sql + eda/outcomes.py. W3 = rules CMP-01..03 v1 (see p01).
-- Denominator: complaints with non-null resolution_days (resolved/closed), whole window.
WITH c AS (
    SELECT resolution_days, status,
           (category = 'Transactions' AND case_type IN ('Claim', 'Complaint', 'Request'))
           OR (category = 'Fees' AND case_type IN ('Claim', 'Complaint')) AS is_w3
    FROM complaints
), g AS (
    SELECT 'W3 (CMP-01..03)' AS group_name, * FROM c WHERE is_w3
    UNION ALL
    SELECT 'Whole bank', * FROM c
)
SELECT group_name,
       count(*)                                         AS n_complaints,
       count(resolution_days)                           AS n_with_resolution,
       round(quantile_cont(resolution_days, 0.5), 1)    AS resolution_days_p50,
       round(quantile_cont(resolution_days, 0.95), 1)   AS resolution_days_p95,
       round(100.0 * count(*) FILTER (WHERE status IN ('Resolved', 'Closed')) / count(*), 3) AS pct_resolved_closed
FROM g
GROUP BY group_name
ORDER BY group_name
