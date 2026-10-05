-- Source of amount_gate.by_country.*.usd_rate for CO and AR in contracts/policies.yaml (spec 02 §4.2) [data].
-- Implied rate = amount / amount_usd per gold transaction, by customer country and currency. It only converts a
-- USD amount for the tier thresholds; it is never shown to a customer (spec 02 §4.4 uses the official series).
-- Run from the repo root after `make setup`: duckdb -c ".read queries/policy/implied_usd_rate.sql"
SELECT c.country, t.currency, count(*) AS n,
       round(quantile_cont(t.amount / t.amount_usd, 0.01), 2) AS rate_p01,
       round(median(t.amount / t.amount_usd), 2) AS rate_p50,
       round(quantile_cont(t.amount / t.amount_usd, 0.99), 2) AS rate_p99
FROM read_parquet('data/gold/transactions.parquet') t
JOIN read_parquet('data/gold/customers.parquet') c USING (customer_id)
WHERE t.amount > 0 AND t.amount_usd > 0
GROUP BY 1, 2
ORDER BY 1, 2;
-- Output on gold v1 (2026-10-04):
-- country   | currency | n       | rate_p01 | rate_p50 | rate_p99
-- Argentina | ARS      | 250866  | 349.97   | 350.0    | 350.03
-- Colombia  | COP      | 379188  | 3999.67  | 4000.0   | 4000.32
-- México has only USD rows with amount_usd null, so there is no implied MXN rate: MX 18.0 and BR 5.5 stay [assumption].
