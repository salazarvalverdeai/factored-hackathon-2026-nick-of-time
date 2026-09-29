-- Supports: findings.md §5 (temporal split, by customer, or both?). Temporal cutoff: 2025-07-01.
-- Produces: outputs/tables/05_split_feasibility.csv (via eda/labels.py).
WITH i AS (SELECT customer_id, interaction_date >= TIMESTAMP '2025-07-01' AS is_test FROM call_center_interactions),
     cust AS (SELECT customer_id,
                     bool_or(interaction_date >= TIMESTAMP '2025-07-01') AS in_test,
                     bool_or(interaction_date < TIMESTAMP '2025-07-01') AS in_train,
                     count(DISTINCT strftime(interaction_date, '%Y-%m')) AS n_months
              FROM call_center_interactions GROUP BY 1)
SELECT 'interacciones train (< 2025-07-01)' AS metric, count(*) FILTER (WHERE NOT is_test)::DOUBLE AS value FROM i
UNION ALL SELECT 'interacciones test (>= 2025-07-01)', count(*) FILTER (WHERE is_test) FROM i
UNION ALL SELECT 'clientes con contactos', count(*) FROM cust
UNION ALL SELECT '% clientes con contactos en más de un mes', round(100.0 * avg((n_months > 1)::INT), 2) FROM cust
UNION ALL SELECT '% clientes presentes en train y en test', round(100.0 * avg((in_train AND in_test)::INT), 2) FROM cust
UNION ALL SELECT '% interacciones de test cuyo cliente aparece en train',
       round(100.0 * avg(c.in_train::INT), 2) FROM i JOIN cust c USING (customer_id) WHERE i.is_test
