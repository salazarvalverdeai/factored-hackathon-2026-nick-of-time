-- Transactions per month by product type, with the status mix. Backs the volume chart of /data (spec 12 AC-03) [data].
-- Runs on this repo's gold (views transactions, products): see run.py. Aggregate only: no ids, no personal data.
-- Window: gold transactions, 2025-06 to 2026-05 (contracts/gold_contract.md R1: 12 full months), so 12 months, not 2023-2026.
-- product_type: debit = 'Tarjeta Débito', credit = 'Tarjeta Crédito', other = every other product (accounts, loans,
--   investment, insurance) and transactions whose product is not in products (orphans).
-- Status as in the gold column transaction_status (Approved, Declined, Pending, Reversed); pct_* are shares of the row.
WITH t AS (
    SELECT strftime(t.transaction_date, '%Y-%m') AS month,
           CASE p.product_type WHEN 'Tarjeta Débito' THEN 'debit' WHEN 'Tarjeta Crédito' THEN 'credit' ELSE 'other' END AS product_type,
           t.transaction_status AS status
    FROM transactions t LEFT JOIN products p ON p.product_id = t.product_id
)
SELECT month, product_type,
       count(*) AS n_transactions,
       count(*) FILTER (WHERE status = 'Approved') AS n_approved,
       count(*) FILTER (WHERE status = 'Declined') AS n_declined,
       count(*) FILTER (WHERE status = 'Pending') AS n_pending,
       count(*) FILTER (WHERE status = 'Reversed') AS n_reversed,
       round(100.0 * count(*) FILTER (WHERE status = 'Approved') / count(*), 1) AS pct_approved,
       round(100.0 * count(*) FILTER (WHERE status = 'Declined') / count(*), 1) AS pct_declined,
       round(100.0 * count(*) FILTER (WHERE status = 'Pending') / count(*), 1) AS pct_pending
FROM t GROUP BY month, product_type ORDER BY month, product_type
