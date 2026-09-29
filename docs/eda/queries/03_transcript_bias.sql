-- Respalda: workflow_mapping.md (decisión 3 del plan: ¿la cobertura de transcripts y encuestas depende del workflow?).
-- Produce: outputs/tables/03_transcript_bias_by_workflow.csv (vía eda/workflows.py; {case_expr} = reglas de interactions).
WITH s AS (SELECT DISTINCT interaction_id FROM satisfaction_surveys)
SELECT {case_expr} AS rule_id, count(*) AS n,
       sum(has_transcript::INT) AS n_with_transcript,
       count(s.interaction_id) AS n_with_survey
FROM call_center_interactions i LEFT JOIN s USING (interaction_id)
GROUP BY 1
