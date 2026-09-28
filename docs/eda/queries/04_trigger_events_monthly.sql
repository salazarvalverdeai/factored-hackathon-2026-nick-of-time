-- Respalda: sección (2) de los expedientes (eventos disparadores por workflow y mes: declinaciones, reversos,
-- fraude, pagos rechazados/pendientes). Produce: outputs/tables/04_trigger_events_monthly.csv (vía eda/outcomes.py).
-- Plantilla: {case_trx} = reglas de transactions. Meses completos: 2023-07 a 2026-05.
SELECT {case_trx} AS rule_id, strftime(transaction_date, '%Y-%m') AS ym, count(*) AS n
FROM (SELECT x.*, p.product_type FROM transactions x LEFT JOIN products p USING (product_id)) s
WHERE transaction_date >= TIMESTAMP '2023-07-01' AND transaction_date < TIMESTAMP '2026-06-01'
GROUP BY ALL
ORDER BY rule_id, ym
