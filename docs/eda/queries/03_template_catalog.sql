-- Supports: section (8) of the dossiers (catalog of text templates, deduplicated, without identifiers).
-- Produces: outputs/tables/03_template_catalog.csv (via eda/workflows.py).
-- Text and frequencies only: no customer_id, interaction_id, name, document, email or phone.
-- {case_trs} = transcripts rules (assigns a workflow to the customer template); {case_cmp} = complaints rules.
SELECT 'call_transcripts.customer_text' AS field, customer_text AS template, {case_trs} AS rule_id, count(*) AS n
FROM call_transcripts GROUP BY ALL
UNION ALL
SELECT 'call_transcripts.agent_text', agent_text, {case_trs}, count(*) FROM call_transcripts GROUP BY ALL
UNION ALL
SELECT 'complaints.description', description, {case_cmp}, count(*) FROM complaints GROUP BY ALL
UNION ALL
SELECT 'complaints.resolution', resolution, {case_cmp}, count(*) FROM complaints WHERE resolution IS NOT NULL GROUP BY ALL
UNION ALL
SELECT 'satisfaction_surveys.open_comments', open_comments, 'TRANSVERSAL', count(*) FROM satisfaction_surveys
WHERE open_comments IS NOT NULL GROUP BY ALL
