-- The bank's fraud_score on card transactions: share null and counts by band, per country. Backs the score chart of
-- /data (spec 12 AC-03) [data]. It is a score the bank gives each transaction, not a label: this query does not read
-- the label column. Runs on this repo's gold (views transactions, products, customers): see run.py. Aggregate only.
-- Card transaction: product 'Tarjeta Crédito' or 'Tarjeta Débito'. Country of the owning customer ('unknown' if none).
-- Bands as in contracts/policies.yaml zones: < 30 (human), 30-49 (medium), >= 50 (high). null score = no score.
-- pct_* are rounded to 3 decimals: the two upper bands are well under 0.1% of card transactions.
WITH card AS (
    SELECT CASE c.country WHEN 'México' THEN 'MX' WHEN 'Colombia' THEN 'CO' WHEN 'Argentina' THEN 'AR' ELSE 'unknown' END AS country,
           t.fraud_score
    FROM transactions t
    JOIN products p ON p.product_id = t.product_id AND p.product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')
    LEFT JOIN customers c ON c.customer_id = t.customer_id
),
agg AS (
    SELECT country, count(*) AS n_card_transactions,
           count(*) FILTER (WHERE fraud_score IS NULL) AS n_null,
           count(*) FILTER (WHERE fraud_score < 30) AS n_lt30,
           count(*) FILTER (WHERE fraud_score >= 30 AND fraud_score < 50) AS n_30_49,
           count(*) FILTER (WHERE fraud_score >= 50) AS n_ge50
    FROM card GROUP BY ROLLUP (country)
)
SELECT coalesce(country, 'all') AS country, n_card_transactions, n_null, n_lt30, n_30_49, n_ge50,
       round(100.0 * n_null / n_card_transactions, 3) AS pct_null,
       round(100.0 * n_lt30 / n_card_transactions, 3) AS pct_lt30,
       round(100.0 * n_30_49 / n_card_transactions, 3) AS pct_30_49,
       round(100.0 * n_ge50 / n_card_transactions, 3) AS pct_ge50
FROM agg ORDER BY country IS NULL, country
