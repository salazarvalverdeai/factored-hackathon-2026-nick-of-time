-- Supports: findings.md §4, sections (2) and (3) of the dossiers (interaction base with workflow and outcomes).
-- Produces: a temporary table that eda/outcomes.py aggregates into 04_workflow_scorecard.csv, 04_scorecard_by_*.csv,
-- 04_recontact.csv, 04_workflow_demand.csv and 04_discrimination_tests.csv.
-- Template: {case_int} = interactions rules; {case_trs} = transcripts rules (03_workflow_mapping.csv).
-- days_to_next = days until the same customer's next contact (any reason): basis for re-contact.
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
ORDER BY i.interaction_id  -- stable order: the bootstrap and the subsamples depend on the order
