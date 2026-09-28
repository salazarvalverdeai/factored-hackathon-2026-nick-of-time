-- Respalda: mapeo_workflows.md §5 (¿la plantilla del transcript se relaciona con los productos del cliente?).
-- Produce: outputs/tables/03_template_vs_ownership.csv (vía eda/workflows.py).
-- Si el texto reflejara la intención real, los clientes con plantilla "saldo de tarjeta" tendrían más tarjetas.
WITH own AS (
    SELECT customer_id, bool_or(product_type = 'Tarjeta Crédito') AS has_credit_card,
           bool_or(product_type = 'Cuenta Ahorro') AS has_savings
    FROM products GROUP BY 1
),
t AS (
    SELECT CASE WHEN customer_text LIKE '%tarjeta de crédito%' THEN 'saldo_tarjeta_credito'
                WHEN customer_text LIKE '%cuenta de ahorros%' THEN 'saldo_cuenta_ahorros' ELSE 'otra' END AS template_base,
           customer_id
    FROM call_transcripts
)
SELECT template_base AS grp, count(*) AS n,
       round(100.0 * avg(coalesce(has_credit_card, FALSE)::INT), 2) AS pct_owns_credit_card,
       round(100.0 * avg(coalesce(has_savings, FALSE)::INT), 2) AS pct_owns_savings
FROM t LEFT JOIN own USING (customer_id) GROUP BY 1
UNION ALL
SELECT 'todos los clientes', count(*), round(100.0 * avg(coalesce(has_credit_card, FALSE)::INT), 2),
       round(100.0 * avg(coalesce(has_savings, FALSE)::INT), 2)
FROM customers LEFT JOIN own USING (customer_id)
ORDER BY grp
