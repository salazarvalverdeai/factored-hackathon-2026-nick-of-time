-- Respalda: findings.md §5 (dataset del chequeo de señal aprendible para is_fraud, Declined y Reversed).
-- Muestra reproducible de ~1.2M transacciones sobre 4.4M: hash(transaction_id) % 1000 < 271 (determinista, no
-- depende de hilos ni de semilla; el reservoir de DuckDB no garantiza repetibilidad con multithreading).
-- Features previas a la autorización. Excluidas: response_code y transaction_status (resultado), is_fraud cuando el
-- label es otro no se usa como feature. fraud_score se evalúa aparte como "score existente", no como feature.
WITH s AS (SELECT * FROM transactions WHERE hash(transaction_id) % 1000 < 271)
SELECT s.transaction_date,
       s.is_fraud, s.transaction_status = 'Declined' AS is_declined, s.transaction_status = 'Reversed' AS is_reversed,
       s.fraud_score,
       s.transaction_type, s.channel, s.currency, coalesce(s.merchant_category, '(nulo)') AS merchant_category,
       ln(1 + CASE WHEN s.currency = 'USD' THEN s.amount ELSE s.amount_usd END) AS log_amount_usd,
       (replace(s.transaction_country, 'Mexico', 'México') <> c.country)::INT AS is_foreign,
       hour(s.transaction_date) AS hour_of_day, isodow(s.transaction_date) AS day_of_week,
       p.product_type, date_diff('day', p.opening_date, s.transaction_date::DATE) AS product_age_days,
       c.segment, c.country, c.credit_score
FROM s LEFT JOIN products p USING (product_id) LEFT JOIN customers c ON c.customer_id = s.customer_id
ORDER BY s.transaction_id
