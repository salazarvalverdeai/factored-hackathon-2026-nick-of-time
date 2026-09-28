-- Respalda: mapeo_workflows.md (acuerdo entre el motivo de la interacción y la plantilla del transcript;
-- reemplaza el acuerdo motivo vs detected_intents, que tiene un solo valor).
-- Produce: outputs/tables/03_reason_vs_text_agreement.csv (vía eda/workflows.py).
-- {case_int} = reglas de interactions; {case_trs} = reglas de transcripts (cada una sobre su propia tabla).
WITH i AS (SELECT interaction_id, reason_category, {case_int} AS rule_int FROM call_center_interactions),
     t AS (SELECT interaction_id, {case_trs} AS rule_trs FROM call_transcripts)
SELECT i.reason_category, i.rule_int, t.rule_trs, count(*) AS n
FROM t JOIN i USING (interaction_id)
GROUP BY ALL
