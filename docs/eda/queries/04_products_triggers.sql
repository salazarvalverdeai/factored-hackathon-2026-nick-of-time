-- Respalda: sección (2) de los expedientes W2 y W4 (cartera y estados al corte: foto única).
-- Produce: outputs/tables/04_products_by_status.csv (vía eda/outcomes.py).
SELECT product_type, product_status, count(*) AS n,
       count(*) FILTER (WHERE days_past_due > 0) AS n_days_past_due_gt0,
       count(days_past_due) AS n_days_past_due_known
FROM products
GROUP BY ALL
ORDER BY product_type, product_status
