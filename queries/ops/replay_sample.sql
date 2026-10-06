-- The replay's contacts (spec 14 §11.2): real approved card charges of MX, CO and AR customers, one seeded sample per
-- contact month of 2026-01..2026-05, sized to the bank's W3 complaints of that month (queries/ops/asis_monthly.sql).
-- The customer reports the charge the day after it (contact_on = charge date + 1). `python -m data.ops replay` runs
-- it with three views: `card` (named columns of gold transactions_enriched, no fraud label), `customers` (id,
-- country) and `quota` (month, n). The order is md5 of the id and a fixed seed, so the sample is the same every run.
WITH c AS (
    SELECT t.transaction_id, t.customer_id, CAST(t.transaction_date AS DATE) AS charged_on, t.amount, t.currency,
           t.merchant_name, t.fraud_score, CAST(t.transaction_date AS DATE) + 1 AS contact_on
    FROM card t JOIN customers k USING (customer_id)
    WHERE t.product_type IN ('Tarjeta Débito', 'Tarjeta Crédito') AND t.transaction_status = 'Approved'
      AND k.country IN ('México', 'Colombia', 'Argentina')
), r AS (
    SELECT *, strftime(contact_on, '%Y-%m') AS month,
           row_number() OVER (PARTITION BY strftime(contact_on, '%Y-%m')
                              ORDER BY md5(transaction_id || ':nick-of-time-replay-v1')) AS k
    FROM c
    WHERE contact_on >= DATE '2026-01-01' AND contact_on < DATE '2026-06-01'
)
SELECT r.* EXCLUDE (k)
FROM r JOIN quota q USING (month)
WHERE r.k <= q.n
ORDER BY month, r.k
