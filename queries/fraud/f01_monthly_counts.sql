-- Spec 17 T1 (AC-01, AC-05, ADR 0022): monthly transactions and frauds, all products and cards.
-- Views expected: transactions_enriched, transaction_labels. Approved/Pending only (spec 17 §4.1).
-- Labels are joined ONLY for months before the test window (2026-04-01); test months report n_fraud = NULL
-- (transactions are counted, labels are not read). Test labels belong to the evaluation step (task 17c).
WITH t AS (
    SELECT transaction_id,
           CAST(date_trunc('month', transaction_date) AS DATE) AS month,
           product_type IN ('Tarjeta Crédito', 'Tarjeta Débito') AS is_card
    FROM transactions_enriched
    WHERE transaction_status IN ('Approved', 'Pending')
),
lab AS (
    SELECT t.transaction_id, l.is_fraud
    FROM t JOIN transaction_labels l USING (transaction_id)
    WHERE t.month < DATE '2026-04-01'
)
SELECT t.month,
       count(*)                                  AS n_transactions,
       count(*) FILTER (WHERE t.is_card)         AS n_transactions_cards,
       CASE WHEN t.month < DATE '2026-04-01'
            THEN count(*) FILTER (WHERE lab.is_fraud) END                    AS n_fraud,
       CASE WHEN t.month < DATE '2026-04-01'
            THEN count(*) FILTER (WHERE lab.is_fraud AND t.is_card) END      AS n_fraud_cards
FROM t LEFT JOIN lab USING (transaction_id)
GROUP BY t.month
ORDER BY t.month;
