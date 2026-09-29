-- Supports: workflow_mapping.md (plan decision 3: does transcript and survey coverage depend on the workflow?).
-- Produces: outputs/tables/03_transcript_bias_by_workflow.csv (via eda/workflows.py; {case_expr} = interactions rules).
WITH s AS (SELECT DISTINCT interaction_id FROM satisfaction_surveys)
SELECT {case_expr} AS rule_id, count(*) AS n,
       sum(has_transcript::INT) AS n_with_transcript,
       count(s.interaction_id) AS n_with_survey
FROM call_center_interactions i LEFT JOIN s USING (interaction_id)
GROUP BY 1
