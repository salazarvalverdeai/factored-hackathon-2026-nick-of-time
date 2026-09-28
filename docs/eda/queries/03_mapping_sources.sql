-- Respalda: mapeo_workflows.md (relaciones sobre las que se aplican las reglas de 03_workflow_mapping.csv).
-- eda/workflows.py lee este archivo y separa cada bloque por su marcador "-- source: <nombre>".
-- Cada bloque es una subconsulta con las columnas que usan las condiciones de las reglas de esa fuente.
-- source: interactions
SELECT * FROM call_center_interactions
-- source: transcripts
SELECT * FROM call_transcripts
-- source: complaints
SELECT * FROM complaints
-- source: transactions
SELECT x.*, p.product_type FROM transactions x LEFT JOIN products p USING (product_id)
-- source: products
SELECT * FROM products
-- source: digital_events
SELECT * FROM digital_events
