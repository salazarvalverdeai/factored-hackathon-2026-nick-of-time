-- Supports: findings.md §5 (dataset for the learnable-signal check on is_fraud, Declined and Reversed).
-- Reproducible sample of ~1.2M out of 4.4M transactions: hash(transaction_id) % 1000 < 271 (deterministic, does not
-- depend on threads or on a seed; DuckDB's reservoir does not guarantee repeatability with multithreading).
-- Features prior to authorization. Excluded: response_code and transaction_status (outcome); is_fraud is not used
-- as a feature when the label is another one. fraud_score is evaluated separately as an "existing score", not as a feature.
WITH s AS (SELECT * FROM transactions WHERE hash(transaction_id) % 1000 < 271)
SELECT s.transaction_date,
       s.is_fraud, s.transaction_status = 'Declined' AS is_declined, s.transaction_status = 'Reversed' AS is_reversed,
       s.fraud_score,
       s.transaction_type, s.channel, s.currency, coalesce(s.merchant_category, '(null)') AS merchant_category,
       ln(1 + CASE WHEN s.currency = 'USD' THEN s.amount ELSE s.amount_usd END) AS log_amount_usd,
       (replace(s.transaction_country, 'Mexico', 'México') <> c.country)::INT AS is_foreign,
       hour(s.transaction_date) AS hour_of_day, isodow(s.transaction_date) AS day_of_week,
       p.product_type, date_diff('day', p.opening_date, s.transaction_date::DATE) AS product_age_days,
       c.segment, c.country, c.credit_score
FROM s LEFT JOIN products p USING (product_id) LEFT JOIN customers c ON c.customer_id = s.customer_id
ORDER BY s.transaction_id
