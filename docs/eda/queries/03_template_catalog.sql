-- Respalda: sección (8) de los expedientes (catálogo de plantillas de texto, deduplicado, sin identificadores).
-- Produce: outputs/tables/03_template_catalog.csv (vía eda/workflows.py).
-- Solo texto y frecuencias: ningún customer_id, interaction_id, nombre, documento, email ni teléfono.
-- {case_trs} = reglas de transcripts (asigna workflow a la plantilla del cliente); {case_cmp} = reglas de complaints.
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
