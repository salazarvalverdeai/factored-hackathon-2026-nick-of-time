-- Supports: data_quality.md §B2 (are the nulls in fields used by phases 4-6 structural or random?).
-- Produces: outputs/tables/01_null_patterns.csv (via eda/quality.py).
-- wait_time_seconds and duration_seconds feed the cost proxy; credit_score and income feed W4.
SELECT 'call_center_interactions' AS tbl, 'wait_time_seconds' AS col, 'channel' AS dimension, channel AS value,
       count(*) AS n, round(100.0 * avg((wait_time_seconds IS NULL)::INT), 2) AS pct_null
FROM call_center_interactions GROUP BY channel
UNION ALL
SELECT 'call_center_interactions', 'wait_time_seconds', 'interaction_type', interaction_type, count(*),
       round(100.0 * avg((wait_time_seconds IS NULL)::INT), 2)
FROM call_center_interactions GROUP BY interaction_type
UNION ALL
SELECT 'call_center_interactions', 'wait_time_seconds', 'reason_category', reason_category, count(*),
       round(100.0 * avg((wait_time_seconds IS NULL)::INT), 2)
FROM call_center_interactions GROUP BY reason_category
UNION ALL
SELECT 'call_center_interactions', 'customer_detected_accent', 'channel', channel, count(*),
       round(100.0 * avg((customer_detected_accent IS NULL)::INT), 2)
FROM call_center_interactions GROUP BY channel
UNION ALL
SELECT 'customers', 'credit_score', 'segment', segment, count(*), round(100.0 * avg((credit_score IS NULL)::INT), 2)
FROM customers GROUP BY segment
UNION ALL
SELECT 'customers', 'estimated_monthly_income', 'segment', segment, count(*),
       round(100.0 * avg((estimated_monthly_income IS NULL)::INT), 2)
FROM customers GROUP BY segment
UNION ALL
SELECT 'products', 'days_past_due', 'product_type', product_type, count(*), round(100.0 * avg((days_past_due IS NULL)::INT), 2)
FROM products GROUP BY product_type
UNION ALL
SELECT 'products', 'credit_limit', 'product_type', product_type, count(*), round(100.0 * avg((credit_limit IS NULL)::INT), 2)
FROM products GROUP BY product_type
UNION ALL
SELECT 'digital_events', 'customer_id', 'event_type', event_type, count(*), round(100.0 * avg((customer_id IS NULL)::INT), 2)
FROM digital_events GROUP BY event_type
ORDER BY tbl, col, dimension, value
