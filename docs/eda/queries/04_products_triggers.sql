-- Supports: section (2) of the W2 and W4 dossiers (portfolio and statuses at the cutoff: single snapshot).
-- Produces: outputs/tables/04_products_by_status.csv (via eda/outcomes.py).
SELECT product_type, product_status, count(*) AS n,
       count(*) FILTER (WHERE days_past_due > 0) AS n_days_past_due_gt0,
       count(days_past_due) AS n_days_past_due_known
FROM products
GROUP BY ALL
ORDER BY product_type, product_status
