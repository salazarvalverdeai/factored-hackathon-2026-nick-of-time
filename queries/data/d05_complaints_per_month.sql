-- Complaints per month by category, with the W3 share line. Backs the complaints chart of /data (spec 12 AC-03) [data].
-- Runs on this repo's gold (view complaints): see run.py. Aggregate only: no ids, no text.
-- W3 = rules CMP-01..03 v1, the same as queries/pitch/p01_w3_share_complaints.sql:
--   CMP-01/02 category = 'Transactions' AND case_type IN ('Claim', 'Complaint', 'Request'); CMP-03 category = 'Fees' AND case_type IN ('Claim', 'Complaint').
-- Window: every complaint in gold, creation month 2023-06 to 2026-06 (the first and last months are partial).
-- n_month and n_w3_month repeat on each category row of a month, so the share line needs no second query.
WITH c AS (
    SELECT strftime(creation_date, '%Y-%m') AS month, category,
           (category = 'Transactions' AND case_type IN ('Claim', 'Complaint', 'Request'))
           OR (category = 'Fees' AND case_type IN ('Claim', 'Complaint')) AS is_w3
    FROM complaints
),
g AS (
    SELECT month, category, count(*) AS n_complaints, count(*) FILTER (WHERE is_w3) AS n_w3 FROM c GROUP BY month, category
)
SELECT month, category, n_complaints, n_w3,
       sum(n_complaints) OVER (PARTITION BY month)::BIGINT AS n_month,
       sum(n_w3) OVER (PARTITION BY month)::BIGINT AS n_w3_month,
       round(100.0 * sum(n_w3) OVER (PARTITION BY month) / sum(n_complaints) OVER (PARTITION BY month), 1) AS pct_w3_month
FROM g ORDER BY month, category
