-- Can a W3 complaint be linked to the card transaction it disputes? Backs the "Dataset limitations" card of /data
-- (spec 12 AC-03) [data]. Runs on this repo's gold (views complaints, transactions, products): see run.py.
-- W3 = rules CMP-01..03 v1, as in queries/pitch/p01_w3_share_complaints.sql.
-- Window: complaints created in [2025-07-01, 2026-06-01), so the whole 30-day look-back falls inside the gold
--   transactions window [2025-06-01, 2026-06-01) (contracts/gold_contract.md R1).
-- Card transaction: a transaction on a 'Tarjeta Crédito' or 'Tarjeta Débito' product of the same customer, dated in
--   the 30 days before the complaint was created. Amount match: same currency and |amount − claimed| ≤ 2% of claimed.
-- The control row (the other complaints, same window) shows the W3 rate is no higher than for unrelated complaints.
WITH c AS (
    SELECT complaint_id, customer_id, creation_date, claimed_amount, currency,
           qc_affected_product_other_customer, affected_product_id,
           (category = 'Transactions' AND case_type IN ('Claim', 'Complaint', 'Request'))
           OR (category = 'Fees' AND case_type IN ('Claim', 'Complaint')) AS is_w3
    FROM complaints
    WHERE creation_date >= TIMESTAMP '2025-07-01' AND creation_date < TIMESTAMP '2026-06-01'
),
card AS (
    SELECT t.customer_id, t.transaction_date, t.amount, t.currency
    FROM transactions t JOIN products p ON p.product_id = t.product_id
    WHERE p.product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')
),
linked AS (
    SELECT c.complaint_id, c.customer_id, c.is_w3, c.claimed_amount,
           bool_or(k.currency = c.currency AND abs(k.amount - c.claimed_amount) <= 0.02 * c.claimed_amount) AS amount_match
    FROM c JOIN card k ON k.customer_id = c.customer_id
     AND k.transaction_date >= c.creation_date - INTERVAL 30 DAY AND k.transaction_date < c.creation_date
    GROUP BY ALL
)
SELECT 'w3_complaints_with_card_txn_30d' AS metric,
       (SELECT count(*) FROM linked WHERE is_w3) AS numerator, (SELECT count(*) FROM c WHERE is_w3) AS denominator
UNION ALL
SELECT 'w3_complainants_with_card_txn_30d',
       (SELECT count(DISTINCT customer_id) FROM linked WHERE is_w3), (SELECT count(DISTINCT customer_id) FROM c WHERE is_w3)
UNION ALL
SELECT 'other_complaints_with_card_txn_30d',
       (SELECT count(*) FROM linked WHERE NOT is_w3), (SELECT count(*) FROM c WHERE NOT is_w3)
UNION ALL
SELECT 'w3_claimed_amount_matches_card_txn_2pct',
       (SELECT count(*) FROM linked WHERE is_w3 AND amount_match),
       (SELECT count(*) FROM linked WHERE is_w3 AND claimed_amount IS NOT NULL)
UNION ALL
SELECT 'w3_affected_product_of_other_customer',
       (SELECT count(*) FROM c WHERE is_w3 AND qc_affected_product_other_customer),
       (SELECT count(*) FROM c WHERE is_w3 AND affected_product_id IS NOT NULL)
