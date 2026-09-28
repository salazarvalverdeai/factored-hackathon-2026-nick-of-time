-- Respalda: calidad_datos.md §B5 (moneda de productos y transacciones según el país del cliente; el diccionario
-- anuncia MXN, COP, ARS, USD y en products/transactions no aparece MXN).
-- Produce: outputs/tables/01_currency_by_country.csv (vía eda/quality.py).
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
