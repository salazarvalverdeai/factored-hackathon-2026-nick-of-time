-- Supports: data_quality.md §B5 (is sla_breached consistent with duration, status and priority?).
-- If % SLA breached depends on neither resolution_days nor status, the scorecard metric is generator noise.
-- Produces: outputs/tables/01_complaints_sla_consistency.csv (via eda/quality.py).
SELECT 'resolution_days' AS dimension,
       CASE WHEN resolution_days IS NULL THEN 'unresolved (null)'
            WHEN resolution_days <= 5 THEN '01-05' WHEN resolution_days <= 10 THEN '06-10'
            WHEN resolution_days <= 15 THEN '11-15' WHEN resolution_days <= 20 THEN '16-20'
            WHEN resolution_days <= 25 THEN '21-25' ELSE '26-30' END AS value,
       count(*) AS n, count(sla_breached) AS n_sla_known, round(100.0 * avg(sla_breached::INT), 2) AS pct_sla_breached
FROM complaints GROUP BY ALL
UNION ALL
SELECT 'status', status, count(*), count(sla_breached), round(100.0 * avg(sla_breached::INT), 2) FROM complaints GROUP BY ALL
UNION ALL
SELECT 'priority', priority, count(*), count(sla_breached), round(100.0 * avg(sla_breached::INT), 2) FROM complaints GROUP BY ALL
UNION ALL
SELECT 'case_type', case_type, count(*), count(sla_breached), round(100.0 * avg(sla_breached::INT), 2) FROM complaints GROUP BY ALL
ORDER BY dimension, value
