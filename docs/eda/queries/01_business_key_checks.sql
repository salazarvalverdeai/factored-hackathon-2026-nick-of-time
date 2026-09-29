-- Supports: data_quality.md §B1 (duplicates under loose business keys, shared emails) and §A5/§B8 (template
-- texts). Produces: outputs/tables/01_business_key_checks.csv (via eda/quality.py).
-- n_extra = rows - distinct key values ("surplus" rows if the key were unique).
SELECT 'call_center_interactions' AS tbl, '(customer_id, interaction_date)' AS key_def,
       count(*) AS n_rows, count(DISTINCT (customer_id, interaction_date)) AS n_distinct FROM call_center_interactions
UNION ALL SELECT 'call_center_interactions', '(customer_id, día, reason_category, channel)',
       count(*), count(DISTINCT (customer_id, interaction_date::DATE, reason_category, channel)) FROM call_center_interactions
UNION ALL SELECT 'transactions', '(product_id, transaction_date, amount)',
       count(*), count(DISTINCT (product_id, transaction_date, amount)) FROM transactions
UNION ALL SELECT 'transactions', '(customer_id, día, amount, transaction_type)',
       count(*), count(DISTINCT (customer_id, transaction_date::DATE, amount, transaction_type)) FROM transactions
UNION ALL SELECT 'complaints', '(customer_id, creation_date)',
       count(*), count(DISTINCT (customer_id, creation_date)) FROM complaints
UNION ALL SELECT 'customers', '(document_number, document_type)',
       count(*), count(DISTINCT (document_number, document_type)) FROM customers
UNION ALL SELECT 'customers', '(first_name, last_name, date_of_birth)',
       count(*), count(DISTINCT (first_name, last_name, date_of_birth)) FROM customers
UNION ALL SELECT 'customers', 'email (no nulo)',
       count(email), count(DISTINCT email) FROM customers
UNION ALL SELECT 'customers', 'clientes cuyo email lo comparte otro cliente (n_distinct = clientes afectados)',
       count(email), (SELECT count(*) FROM customers WHERE email IN (SELECT email FROM customers GROUP BY email HAVING count(*) > 1))
       FROM customers
UNION ALL SELECT 'call_transcripts', 'full_text', count(full_text), count(DISTINCT full_text) FROM call_transcripts
UNION ALL SELECT 'call_transcripts', 'customer_text', count(customer_text), count(DISTINCT customer_text) FROM call_transcripts
UNION ALL SELECT 'call_transcripts', 'agent_text', count(agent_text), count(DISTINCT agent_text) FROM call_transcripts
UNION ALL SELECT 'complaints', 'description', count(description), count(DISTINCT description) FROM complaints
