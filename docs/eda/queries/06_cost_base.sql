-- Respalda: findings.md §6 y sección (5) de los expedientes (proxies de costo e insumos del business case).
-- Produce: agregados por (regla de interacción, regla de transcript) que eda/cost.py combina en
-- 06_cost_by_workflow.csv y 06_business_case_inputs.csv. Meses completos: 2023-07 a 2026-05 (35).
-- Plantilla: {case_int}, {case_trs} = reglas de 03_workflow_mapping.csv.
-- automatable_bound = resuelto en primer contacto, sin escalar, sin seguimiento y sin complaint del mismo cliente en
-- los 30 días siguientes (cota superior de "automatizable seguro": es una definición [supuesto] sobre datos medidos).
WITH t AS (SELECT interaction_id, {case_trs} AS rule_trs FROM call_transcripts),
     i AS (
        SELECT i.*, {case_int} AS rule_int
        FROM call_center_interactions i
        WHERE interaction_date >= TIMESTAMP '2023-07-01' AND interaction_date < TIMESTAMP '2026-06-01'
     ),
     k AS (
        SELECT DISTINCT i.interaction_id
        FROM i JOIN complaints c ON c.customer_id = i.customer_id
             AND c.creation_date > i.interaction_date AND c.creation_date <= i.interaction_date + INTERVAL 30 DAY
     )
SELECT i.rule_int, t.rule_trs,
       count(*) AS n,
       count(i.duration_seconds) AS n_with_duration,
       sum(i.duration_seconds) / 60.0 AS handle_minutes,
       sum(i.wait_time_seconds) / 60.0 AS wait_minutes,
       count(i.wait_time_seconds) AS n_with_wait,
       count(*) FILTER (WHERE i.channel = 'Phone') AS n_phone,
       count(*) FILTER (WHERE k.interaction_id IS NOT NULL) AS n_complaint_30d,
       count(*) FILTER (WHERE i.was_resolved AND NOT i.was_escalated AND NOT i.requires_followup
                        AND k.interaction_id IS NULL) AS n_automatable_bound
FROM i
LEFT JOIN t USING (interaction_id)
LEFT JOIN k USING (interaction_id)
GROUP BY ALL
