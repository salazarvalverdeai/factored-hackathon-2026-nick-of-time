-- Supports: workflow_mapping.md §5 (is the transcript template related to the customer's products?).
-- Produces: outputs/tables/03_template_vs_ownership.csv (via eda/workflows.py).
-- If the text reflected the real intent, customers with the "card balance" template would own more cards.
WITH own AS (
    SELECT customer_id, bool_or(product_type = 'Tarjeta Crédito') AS has_credit_card,
           bool_or(product_type = 'Cuenta Ahorro') AS has_savings
    FROM products GROUP BY 1
),
t AS (
    SELECT CASE WHEN customer_text LIKE '%tarjeta de crédito%' THEN 'credit_card_balance'
                WHEN customer_text LIKE '%cuenta de ahorros%' THEN 'savings_account_balance' ELSE 'other' END AS template_base,
           customer_id
    FROM call_transcripts
)
SELECT template_base AS grp, count(*) AS n,
       round(100.0 * avg(coalesce(has_credit_card, FALSE)::INT), 2) AS pct_owns_credit_card,
       round(100.0 * avg(coalesce(has_savings, FALSE)::INT), 2) AS pct_owns_savings
FROM t LEFT JOIN own USING (customer_id) GROUP BY 1
UNION ALL
SELECT 'all customers', count(*), round(100.0 * avg(coalesce(has_credit_card, FALSE)::INT), 2),
       round(100.0 * avg(coalesce(has_savings, FALSE)::INT), 2)
FROM customers LEFT JOIN own USING (customer_id)
ORDER BY grp
