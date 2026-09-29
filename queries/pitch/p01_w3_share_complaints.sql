-- Pitch number: "36.4% of complaints" and "679 cases/month" of unrecognized charges and wrongful charges (W3).
-- EDA backing: outputs/tables/03_coverage_summary.csv (pct_W3_disputes) and 04_workflow_scorecard.csv
--   (W3_disputes, volumen_mensual_complaints), via docs/eda/queries/03_apply_mapping.sql and 04_complaints_base.sql.
-- W3 = rules CMP-01..03 v1 from docs/eda/queries/03_workflow_mapping.csv:
--   CMP-01 category = 'Transactions' AND case_type = 'Claim'
--   CMP-02 category = 'Transactions' AND case_type IN ('Complaint', 'Request')
--   CMP-03 category = 'Fees' AND case_type IN ('Claim', 'Complaint')
-- Denominator of the %: all complaints (whole window). Per month: full months 2023-07..2026-05 (35).
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
