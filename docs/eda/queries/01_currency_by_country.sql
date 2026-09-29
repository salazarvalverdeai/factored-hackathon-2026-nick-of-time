-- Supports: data_quality.md §B5 (currency of products and transactions by customer country; the data dictionary
-- lists MXN, COP, ARS, USD, and MXN does not appear in products/transactions).
-- Produces: outputs/tables/01_currency_by_country.csv (via eda/quality.py).
SELECT 'products' AS tbl, c.country, p.currency, count(*) AS n,
       round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY c.country), 2) AS pct_within_country
FROM products p JOIN customers c USING (customer_id) GROUP BY c.country, p.currency
UNION ALL
SELECT 'transactions', c.country, x.currency, count(*),
       round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY c.country), 2)
FROM transactions x JOIN customers c USING (customer_id) GROUP BY c.country, x.currency
UNION ALL
SELECT 'complaints', c.country, coalesce(k.currency, '(nulo)'), count(*),
       round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY c.country), 2)
FROM complaints k JOIN customers c USING (customer_id) GROUP BY c.country, k.currency
ORDER BY tbl, country, n DESC
