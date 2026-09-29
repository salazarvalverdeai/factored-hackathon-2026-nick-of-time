-- Supports: findings.md §2 and section (2) of the dossiers (monthly volume by dimension).
-- Produces: outputs/tables/02_monthly_volume.csv (via eda/demand.py).
-- Long format: dimension × value × month. full_month = full month within the window (Jul 2023 – May 2026, 35 months).
-- country and segment come from customers (single snapshot at the cutoff).
WITH i AS (
    SELECT strftime(i.interaction_date, '%Y-%m') AS ym, i.reason_category, i.channel, i.interaction_type,
           c.country, c.segment
    FROM call_center_interactions i LEFT JOIN customers c USING (customer_id)
)
SELECT 'total' AS dimension, 'total' AS value, ym, count(*) AS n FROM i GROUP BY ym
UNION ALL SELECT 'reason_category', reason_category, ym, count(*) FROM i GROUP BY reason_category, ym
UNION ALL SELECT 'channel', channel, ym, count(*) FROM i GROUP BY channel, ym
UNION ALL SELECT 'interaction_type', interaction_type, ym, count(*) FROM i GROUP BY interaction_type, ym
UNION ALL SELECT 'country', country, ym, count(*) FROM i GROUP BY country, ym
UNION ALL SELECT 'segment', segment, ym, count(*) FROM i GROUP BY segment, ym
ORDER BY dimension, value, ym
