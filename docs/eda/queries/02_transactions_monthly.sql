-- Supports: dossiers W1–W3 §(2) (volume of transactional events that can trigger contacts:
-- payments/transfers, declines, reversals, fraud). Produces: outputs/tables/02_transactions_monthly.csv.
WITH x AS (
    SELECT strftime(x.transaction_date, '%Y-%m') AS ym, x.transaction_type, x.transaction_status, x.is_fraud,
           p.product_type
    FROM transactions x LEFT JOIN products p USING (product_id)
)
SELECT 'total' AS dimension, 'total' AS value, ym, count(*) AS n FROM x GROUP BY ym
UNION ALL SELECT 'transaction_type', transaction_type, ym, count(*) FROM x GROUP BY transaction_type, ym
UNION ALL SELECT 'transaction_status', transaction_status, ym, count(*) FROM x GROUP BY transaction_status, ym
UNION ALL SELECT 'is_fraud', is_fraud::VARCHAR, ym, count(*) FROM x GROUP BY is_fraud, ym
UNION ALL SELECT 'product_type', product_type, ym, count(*) FROM x GROUP BY product_type, ym
UNION ALL SELECT 'declined_by_product_type', product_type, ym, count(*) FROM x WHERE transaction_status = 'Declined' GROUP BY product_type, ym
ORDER BY dimension, value, ym
