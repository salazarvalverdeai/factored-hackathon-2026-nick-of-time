-- Respalda: findings.md §2 ("a quién afecta": contactos por cliente según segmento y país, sobre toda la ventana).
-- Produce: outputs/tables/02_contact_rate.csv (vía eda/demand.py). segment/country = foto única de customers.
WITH k AS (SELECT customer_id, count(*) AS n_int FROM call_center_interactions GROUP BY 1)
SELECT 'segment' AS dimension, c.segment AS value, count(*) AS n_customers,
       sum(coalesce(k.n_int, 0)) AS n_interactions,
       round(avg(coalesce(k.n_int, 0)), 3) AS interactions_per_customer,
       round(100.0 * avg((k.n_int IS NOT NULL)::INT), 2) AS pct_customers_with_contact
FROM customers c LEFT JOIN k USING (customer_id) GROUP BY c.segment
UNION ALL
SELECT 'country', c.country, count(*), sum(coalesce(k.n_int, 0)), round(avg(coalesce(k.n_int, 0)), 3),
       round(100.0 * avg((k.n_int IS NOT NULL)::INT), 2)
FROM customers c LEFT JOIN k USING (customer_id) GROUP BY c.country
UNION ALL
SELECT 'total', 'total', count(*), sum(coalesce(k.n_int, 0)), round(avg(coalesce(k.n_int, 0)), 3),
       round(100.0 * avg((k.n_int IS NOT NULL)::INT), 2)
FROM customers c LEFT JOIN k USING (customer_id)
ORDER BY dimension, value
