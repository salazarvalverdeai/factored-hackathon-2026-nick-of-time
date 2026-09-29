-- Supports: workflow_mapping.md (agreement between the interaction reason and the transcript template;
-- replaces the reason vs detected_intents agreement, since detected_intents has a single value).
-- Produces: outputs/tables/03_reason_vs_text_agreement.csv (via eda/workflows.py).
-- {case_int} = interactions rules; {case_trs} = transcripts rules (each on its own table).
WITH i AS (SELECT interaction_id, reason_category, {case_int} AS rule_int FROM call_center_interactions),
     t AS (SELECT interaction_id, {case_trs} AS rule_trs FROM call_transcripts)
SELECT i.reason_category, i.rule_int, t.rule_trs, count(*) AS n
FROM t JOIN i USING (interaction_id)
GROUP BY ALL
