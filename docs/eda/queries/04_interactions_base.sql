-- Respalda: findings.md §4, sección (2) y (3) de los expedientes (base de interacciones con workflow y outcomes).
-- Produce: tabla temporal que eda/outcomes.py agrega en 04_workflow_scorecard.csv, 04_scorecard_by_*.csv,
-- 04_recontact.csv, 04_workflow_demand.csv y 04_discrimination_tests.csv.
-- Plantilla: {case_int} = reglas de interactions; {case_trs} = reglas de transcripts (03_workflow_mapping.csv).
-- days_to_next = días hasta el siguiente contacto del mismo cliente (cualquier motivo): base del re-contacto.
WITH t AS (SELECT interaction_id, {case_trs} AS rule_trs FROM call_transcripts),
     nxt AS (
        SELECT interaction_id,
               date_diff('minute', interaction_date,
                         lead(interaction_date) OVER (PARTITION BY customer_id ORDER BY interaction_date)) / 1440.0
               AS days_to_next
        FROM call_center_interactions
     )
SELECT i.interaction_id, i.interaction_date, strftime(i.interaction_date, '%Y-%m') AS ym,
       i.channel, i.interaction_type, i.reason_category, i.duration_seconds, i.wait_time_seconds,
       i.was_resolved, i.was_escalated, i.requires_followup, i.detected_sentiment, i.customer_detected_accent,
       {case_int} AS rule_int, t.rule_trs,
       c.country, c.segment, a.experience_level AS agent_experience, a.agent_type,
       s.survey_type, s.main_score, s.nps_category,
       nxt.days_to_next
FROM call_center_interactions i
LEFT JOIN t USING (interaction_id)
LEFT JOIN nxt USING (interaction_id)
LEFT JOIN customers c USING (customer_id)
LEFT JOIN service_agents a USING (agent_id)
LEFT JOIN satisfaction_surveys s USING (interaction_id)
ORDER BY i.interaction_id  -- orden estable: el bootstrap y los submuestreos dependen del orden
