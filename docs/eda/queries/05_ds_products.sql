-- Respalda: findings.md §5 (dataset del chequeo de señal aprendible para product_status = Blocked en tarjetas y
-- days_past_due > 0 en productos de crédito). Foto única: el estado es al corte, sin fecha del evento; el split
-- temporal es por opening_date. Excluidas: current_balance, last_transaction_date, last_updated (estado al corte).
WITH n AS (SELECT customer_id, count(*) AS n_products FROM products GROUP BY 1)
SELECT p.opening_date, p.product_type,
       p.product_status = 'Blocked' AS is_blocked,
       p.days_past_due > 0 AS is_past_due, p.days_past_due IS NOT NULL AS has_dpd,
       p.currency, p.opening_channel, p.has_linked_app::INT AS has_linked_app,
       ln(1 + p.credit_limit) AS log_credit_limit, p.interest_rate,
       date_diff('day', p.opening_date, DATE '2026-06-17') AS product_age_days,
       n.n_products, c.segment, c.country, c.credit_score, c.estimated_monthly_income, c.customer_status,
       date_diff('day', c.registration_date, p.opening_date::TIMESTAMP) AS tenure_at_opening_days
FROM products p LEFT JOIN customers c USING (customer_id) LEFT JOIN n USING (customer_id)
ORDER BY p.product_id
