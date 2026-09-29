-- Supports: workflow_mapping.md (relations that the rules in 03_workflow_mapping.csv are applied to).
-- eda/workflows.py reads this file and splits it into blocks at each "-- source: <name>" marker.
-- Each block is a subquery with the columns used by the rule conditions of that source.
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
