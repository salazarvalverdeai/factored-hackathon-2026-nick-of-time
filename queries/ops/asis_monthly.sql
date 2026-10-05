-- Bank today [data] (spec 14 §11): the W3 complaints per creation month, 2025-06..2026-05, from gold `complaints`.
-- W3 = rules CMP-01..03 of queries/pitch/p01_w3_share_complaints.sql. `python -m data.ops replay` runs it with a view
-- `complaints` over $GOLD_PATH/complaints.parquet and writes queries/ops/asis_monthly.csv.
--   days_to_first_response: first_response_date − creation_date in days, the closest proxy in the dataset for "time to
--     a receipt with a legal deadline" (the dataset records no receipt); complaints with no first response are left
--     out of it and counted in n_no_first_response.
--   n_escalated: status = 'Escalated' at the dataset's snapshot. n_sla_breached: the dataset's own `sla_breached` flag,
--     by intake (creation) month. resolution_days: shown for the bank only; a person decides it (not simulated).
WITH w AS (
    SELECT strftime(creation_date, '%Y-%m') AS month,
           date_diff('minute', creation_date, first_response_date) / 1440.0 AS frd,
           status, sla_breached, resolution_days
    FROM complaints
    WHERE ((category = 'Transactions' AND case_type IN ('Claim', 'Complaint', 'Request'))
           OR (category = 'Fees' AND case_type IN ('Claim', 'Complaint')))
      AND creation_date >= TIMESTAMP '2025-06-01' AND creation_date < TIMESTAMP '2026-06-01'
)
SELECT coalesce(month, 'total')                     AS month,
       count(*)                                         AS n_complaints,
       count(frd)                                       AS n_first_response,
       count(*) - count(frd)                            AS n_no_first_response,
       round(quantile_cont(frd, 0.5), 3)                AS days_to_first_response_p50,
       round(avg(frd), 3)                               AS days_to_first_response_mean,
       count(*) FILTER (WHERE status = 'Escalated')     AS n_escalated,
       count(*) FILTER (WHERE sla_breached)             AS n_sla_breached,
       count(resolution_days)                           AS n_resolved,
       round(quantile_cont(resolution_days, 0.5), 1)    AS resolution_days_p50
FROM w
GROUP BY ROLLUP (month)                             -- the last row, month 'total', is the 12-month total
ORDER BY month NULLS LAST
