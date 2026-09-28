-- Respalda: findings.md §5 y sección (4) de los expedientes (¿alcanza el texto para un clasificador?).
-- Produce: outputs/tables/05_transcripts_by_workflow.csv (vía eda/labels.py).
-- {case_int} y {case_trs} = reglas de 03_workflow_mapping.csv.
WITH i AS (SELECT interaction_id, {case_int} AS rule_int FROM call_center_interactions),
     t AS (SELECT *, {case_trs} AS rule_trs FROM call_transcripts)
SELECT 'por plantilla (TRS)' AS grouping, t.rule_trs AS rule_id, count(*) AS n_transcripts,
       count(DISTINCT t.customer_text) AS n_distinct_customer_text, count(DISTINCT t.full_text) AS n_distinct_full_text,
       quantile_cont(length(t.full_text), 0.5) AS full_text_chars_p50,
       quantile_cont(length(t.customer_text), 0.5) AS customer_text_chars_p50,
       quantile_cont(len(string_split(t.customer_text, ' ')), 0.5) AS customer_words_p50
FROM t GROUP BY ALL
UNION ALL
SELECT 'por motivo (INT)', i.rule_int, count(*), count(DISTINCT t.customer_text), count(DISTINCT t.full_text),
       quantile_cont(length(t.full_text), 0.5), quantile_cont(length(t.customer_text), 0.5),
       quantile_cont(len(string_split(t.customer_text, ' ')), 0.5)
FROM t JOIN i USING (interaction_id) GROUP BY ALL
ORDER BY grouping, rule_id
