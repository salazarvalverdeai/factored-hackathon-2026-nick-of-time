-- Supports: findings.md §6 and section (5) of the dossiers (cost proxies and business case inputs).
-- Produces: aggregates by (interaction rule, transcript rule) that eda/cost.py combines into
-- 06_cost_by_workflow.csv and 06_business_case_inputs.csv. Full months: 2023-07 to 2026-05 (35).
-- Template: {case_int}, {case_trs} = rules from 03_workflow_mapping.csv.
-- automatable_bound = resolved on first contact, not escalated, no follow-up and no complaint from the same customer in
-- the following 30 days (upper bound of "safely automatable": it is a definition [assumption] over measured data).
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
