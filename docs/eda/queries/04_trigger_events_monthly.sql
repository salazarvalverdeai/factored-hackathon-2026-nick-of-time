-- Supports: section (2) of the dossiers (trigger events by workflow and month: declines, reversals,
-- fraud, rejected/pending payments). Produces: outputs/tables/04_trigger_events_monthly.csv (via eda/outcomes.py).
-- Template: {case_trx} = transactions rules. Full months: 2023-07 to 2026-05.
SELECT {case_trx} AS rule_id, strftime(transaction_date, '%Y-%m') AS ym, count(*) AS n
FROM (SELECT x.*, p.product_type FROM transactions x LEFT JOIN products p USING (product_id)) s
WHERE transaction_date >= TIMESTAMP '2023-07-01' AND transaction_date < TIMESTAMP '2026-06-01'
GROUP BY ALL
ORDER BY rule_id, ym
