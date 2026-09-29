-- Supports: findings.md §5 and section (4) of the dossiers (is the text enough for a classifier?).
-- Produces: outputs/tables/05_transcripts_by_workflow.csv (via eda/labels.py).
-- {case_int} and {case_trs} = rules from 03_workflow_mapping.csv.
WITH i AS (SELECT interaction_id, {case_int} AS rule_int FROM call_center_interactions),
     t AS (SELECT *, {case_trs} AS rule_trs FROM call_transcripts)
SELECT 'by template (TRS)' AS grouping, t.rule_trs AS rule_id, count(*) AS n_transcripts,
       count(DISTINCT t.customer_text) AS n_distinct_customer_text, count(DISTINCT t.full_text) AS n_distinct_full_text,
       quantile_cont(length(t.full_text), 0.5) AS full_text_chars_p50,
       quantile_cont(length(t.customer_text), 0.5) AS customer_text_chars_p50,
       quantile_cont(len(string_split(t.customer_text, ' ')), 0.5) AS customer_words_p50
FROM t GROUP BY ALL
UNION ALL
SELECT 'by reason (INT)', i.rule_int, count(*), count(DISTINCT t.customer_text), count(DISTINCT t.full_text),
       quantile_cont(length(t.full_text), 0.5), quantile_cont(length(t.customer_text), 0.5),
       quantile_cont(len(string_split(t.customer_text, ' ')), 0.5)
FROM t JOIN i USING (interaction_id) GROUP BY ALL
ORDER BY grouping, rule_id
