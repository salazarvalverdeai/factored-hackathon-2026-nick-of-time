-- Spec 17 T1 (AC-01): the time split. One row per Approved/Pending transaction with its window.
-- Windows (spec 17 §4.1): train 2025-06 -> 2026-01, validation 2026-02 -> 2026-03, test 2026-04 -> 2026-05.
-- Uses transactions only, never labels. Agent cases (specs 09, 10) are from May 2026, so they fall in test.
SELECT transaction_id,
       CASE WHEN transaction_date >= TIMESTAMP '2025-06-01' AND transaction_date < TIMESTAMP '2026-02-01' THEN 'train'
            WHEN transaction_date >= TIMESTAMP '2026-02-01' AND transaction_date < TIMESTAMP '2026-04-01' THEN 'validation'
            WHEN transaction_date >= TIMESTAMP '2026-04-01' AND transaction_date < TIMESTAMP '2026-06-01' THEN 'test'
       END AS split_window
FROM transactions_enriched
WHERE transaction_status IN ('Approved', 'Pending')
  AND transaction_date >= TIMESTAMP '2025-06-01' AND transaction_date < TIMESTAMP '2026-06-01';
