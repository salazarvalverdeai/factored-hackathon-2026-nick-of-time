-- Customers and transactions per country (MX, CO, AR) and per segment. Backs the "who is in the data" chart of /data
-- (spec 12 AC-03) [data]. Runs on this repo's gold (views customers, transactions): see run.py. Aggregate only.
-- Country as in gold customers.country (México, Colombia, Argentina). Transactions are attributed to the customer that
-- owns the product (gold_contract R2); transactions without a resolved customer are counted under country 'unknown'.
-- Rows: one per country x segment, plus the country totals (segment 'all').
WITH cu AS (
    SELECT customer_id, segment,
           CASE country WHEN 'México' THEN 'MX' WHEN 'Colombia' THEN 'CO' WHEN 'Argentina' THEN 'AR' ELSE 'other' END AS country
    FROM customers
),
tx AS (
    SELECT customer_id, count(*) AS n FROM transactions GROUP BY customer_id
),
j AS (
    SELECT cu.country, cu.segment, cu.customer_id, coalesce(tx.n, 0) AS n_tx FROM cu LEFT JOIN tx USING (customer_id)
)
SELECT country, segment, count(*) AS n_customers, sum(n_tx)::BIGINT AS n_transactions FROM j GROUP BY country, segment
UNION ALL
SELECT country, 'all', count(*), sum(n_tx)::BIGINT FROM j GROUP BY country
UNION ALL
SELECT 'unknown', 'all', 0, count(*) FROM transactions WHERE customer_id IS NULL OR customer_id NOT IN (SELECT customer_id FROM customers)
ORDER BY country, segment
