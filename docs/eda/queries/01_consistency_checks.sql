-- Supports: data_quality.md §B3 (cross-table consistency: customer ownership, interaction→transcript→survey chain).
-- Produces: outputs/tables/01_consistency_checks.csv (via eda/quality.py).
-- Relevant to the challenge: "per-customer record isolation" and join validity for the scorecard.
WITH tr AS (
    SELECT t.*, i.customer_id AS i_customer_id, i.agent_id AS i_agent_id, i.reason_category AS i_reason_category,
           i.duration_seconds AS i_duration_seconds, i.has_transcript AS i_has_transcript,
           i.interaction_id IS NOT NULL AS has_interaction
    FROM call_transcripts t LEFT JOIN call_center_interactions i USING (interaction_id)
),
sv AS (
    SELECT s.*, i.customer_id AS i_customer_id, i.agent_id AS i_agent_id, i.interaction_date AS i_interaction_date,
           i.interaction_id IS NOT NULL AS has_interaction
    FROM satisfaction_surveys s LEFT JOIN call_center_interactions i USING (interaction_id)
),
tx AS (
    SELECT x.customer_id, x.transaction_date, x.currency, p.customer_id AS p_customer_id, p.opening_date AS p_opening_date,
           p.currency AS p_currency, p.product_id IS NOT NULL AS has_product
    FROM transactions x LEFT JOIN products p USING (product_id)
),
mp AS (
    SELECT i.customer_id, trim(unnest(string_split(i.mentioned_products, ','))) AS product_id
    FROM call_center_interactions i WHERE i.mentioned_products IS NOT NULL
)
SELECT 'call_transcripts' AS tbl, 'C01' AS check_id, 'transcript cuya interacción tiene has_transcript = False' AS rule,
       count(*) FILTER (WHERE NOT i_has_transcript) AS n_violations, count(*) FILTER (WHERE has_interaction) AS n_checked FROM tr
UNION ALL SELECT 'call_center_interactions', 'C02', 'has_transcript = True sin fila en call_transcripts',
       count(*) FILTER (WHERE t.interaction_id IS NULL), count(*)
       FROM call_center_interactions i LEFT JOIN (SELECT DISTINCT interaction_id FROM call_transcripts) t USING (interaction_id)
       WHERE i.has_transcript
UNION ALL SELECT 'call_transcripts', 'C03', 'customer_id del transcript distinto al de la interacción',
       count(*) FILTER (WHERE customer_id <> i_customer_id), count(*) FILTER (WHERE customer_id IS NOT NULL AND i_customer_id IS NOT NULL) FROM tr
UNION ALL SELECT 'call_transcripts', 'C04', 'agent_id del transcript distinto al de la interacción',
       count(*) FILTER (WHERE agent_id <> i_agent_id), count(*) FILTER (WHERE agent_id IS NOT NULL AND i_agent_id IS NOT NULL) FROM tr
UNION ALL SELECT 'call_transcripts', 'C05', 'main_topics distinto de reason_category de la interacción',
       count(*) FILTER (WHERE main_topics <> i_reason_category), count(*) FILTER (WHERE main_topics IS NOT NULL AND i_reason_category IS NOT NULL) FROM tr
UNION ALL SELECT 'call_transcripts', 'C06', 'duration_seconds del transcript distinta a la de la interacción',
       count(*) FILTER (WHERE duration_seconds <> i_duration_seconds), count(*) FILTER (WHERE duration_seconds IS NOT NULL AND i_duration_seconds IS NOT NULL) FROM tr
UNION ALL SELECT 'call_transcripts', 'C07', 'interacciones con más de un transcript',
       count(*) FILTER (WHERE n > 1), count(*) FROM (SELECT interaction_id, count(*) n FROM call_transcripts GROUP BY 1)
UNION ALL SELECT 'satisfaction_surveys', 'C08', 'customer_id de la encuesta distinto al de la interacción',
       count(*) FILTER (WHERE customer_id <> i_customer_id), count(*) FILTER (WHERE customer_id IS NOT NULL AND i_customer_id IS NOT NULL) FROM sv
UNION ALL SELECT 'satisfaction_surveys', 'C09', 'agent_id de la encuesta distinto al de la interacción',
       count(*) FILTER (WHERE agent_id <> i_agent_id), count(*) FILTER (WHERE agent_id IS NOT NULL AND i_agent_id IS NOT NULL) FROM sv
UNION ALL SELECT 'satisfaction_surveys', 'C10', 'survey_date anterior a interaction_date',
       count(*) FILTER (WHERE survey_date < i_interaction_date), count(*) FILTER (WHERE survey_date IS NOT NULL AND i_interaction_date IS NOT NULL) FROM sv
UNION ALL SELECT 'satisfaction_surveys', 'C11', 'interacciones con más de una encuesta',
       count(*) FILTER (WHERE n > 1), count(*) FROM (SELECT interaction_id, count(*) n FROM satisfaction_surveys WHERE interaction_id IS NOT NULL GROUP BY 1)
UNION ALL SELECT 'transactions', 'C12', 'customer_id de la transacción distinto al dueño del producto',
       count(*) FILTER (WHERE customer_id <> p_customer_id), count(*) FILTER (WHERE customer_id IS NOT NULL AND p_customer_id IS NOT NULL) FROM tx
UNION ALL SELECT 'transactions', 'C13', 'transaction_date anterior a la apertura del producto',
       count(*) FILTER (WHERE transaction_date::DATE < p_opening_date), count(*) FILTER (WHERE transaction_date IS NOT NULL AND p_opening_date IS NOT NULL) FROM tx
UNION ALL SELECT 'transactions', 'C14', 'currency de la transacción distinta a la del producto',
       count(*) FILTER (WHERE currency <> p_currency), count(*) FILTER (WHERE currency IS NOT NULL AND p_currency IS NOT NULL) FROM tx
UNION ALL SELECT 'complaints', 'C15', 'affected_product_id pertenece a otro cliente',
       count(*) FILTER (WHERE c.customer_id <> p.customer_id), count(*) FILTER (WHERE c.customer_id IS NOT NULL AND p.customer_id IS NOT NULL)
       FROM complaints c JOIN products p ON c.affected_product_id = p.product_id
UNION ALL SELECT 'call_center_interactions', 'C16', 'producto mencionado pertenece a otro cliente (por ID mencionado)',
       count(*) FILTER (WHERE mp.customer_id <> p.customer_id), count(*) FILTER (WHERE p.customer_id IS NOT NULL)
       FROM mp LEFT JOIN products p USING (product_id)
UNION ALL SELECT 'products', 'C17', 'producto abierto antes del registro del cliente',
       count(*) FILTER (WHERE p.opening_date < c.registration_date::DATE), count(*) FILTER (WHERE p.opening_date IS NOT NULL AND c.registration_date IS NOT NULL)
       FROM products p JOIN customers c USING (customer_id)
UNION ALL SELECT 'call_center_interactions', 'C18', 'customer_detected_accent distinto de customers.detected_accent',
       count(*) FILTER (WHERE i.customer_detected_accent <> c.detected_accent),
       count(*) FILTER (WHERE i.customer_detected_accent IS NOT NULL AND c.detected_accent IS NOT NULL)
       FROM call_center_interactions i JOIN customers c USING (customer_id)
UNION ALL SELECT 'digital_events', 'C20', 'product_id del evento pertenece a otro cliente',
       count(*) FILTER (WHERE e.customer_id <> p.customer_id), count(*) FILTER (WHERE e.customer_id IS NOT NULL AND p.customer_id IS NOT NULL)
       FROM digital_events e JOIN products p USING (product_id)
