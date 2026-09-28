-- Respalda: findings.md §4 y sección (3) de los expedientes (outcomes de complaints por workflow).
-- Produce: tabla temporal que eda/outcomes.py agrega en 04_workflow_scorecard.csv y 04_discrimination_tests.csv.
-- Plantilla: {case_cmp} = reglas de complaints (03_workflow_mapping.csv).
SELECT k.complaint_id, strftime(k.creation_date, '%Y-%m') AS ym, k.case_type, k.category, k.priority,
       k.reception_channel, k.status, k.sla_breached, k.resolution_days, k.claimed_amount, k.compensation_granted,
       k.resolution_satisfaction, k.is_repeat_complainer, {case_cmp} AS rule_cmp, c.country, c.segment
FROM complaints k LEFT JOIN customers c USING (customer_id)
ORDER BY k.complaint_id
