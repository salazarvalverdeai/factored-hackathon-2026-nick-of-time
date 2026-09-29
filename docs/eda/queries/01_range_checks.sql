-- Supports: data_quality.md §B5 (impossible ranges and business rules within each table).
-- Produces: outputs/tables/01_range_checks.csv (via eda/quality.py).
-- Dataset window (data dictionary): 2023-06-17 00:00 → 2026-06-17 23:59:59. S3 upload: 2026-08-31.
-- Each row: table, check id, rule, violations and denominator (rows where the rule can be evaluated).
SELECT 'call_center_interactions' AS tbl, 'R01' AS check_id, 'interaction_date outside the window' AS rule,
       count(*) FILTER (WHERE interaction_date < TIMESTAMP '2023-06-17' OR interaction_date >= TIMESTAMP '2026-06-18') AS n_violations,
       count(interaction_date) AS n_checked FROM call_center_interactions
UNION ALL SELECT 'call_center_interactions', 'R02', 'duration_seconds <= 0',
       count(*) FILTER (WHERE duration_seconds <= 0), count(duration_seconds) FROM call_center_interactions
UNION ALL SELECT 'call_center_interactions', 'R03', 'wait_time_seconds < 0',
       count(*) FILTER (WHERE wait_time_seconds < 0), count(wait_time_seconds) FROM call_center_interactions
UNION ALL SELECT 'call_center_interactions', 'R04', 'sentiment_score outside [-1, 1]',
       count(*) FILTER (WHERE sentiment_score NOT BETWEEN -1 AND 1), count(sentiment_score) FROM call_center_interactions
UNION ALL SELECT 'call_center_interactions', 'R05', 'detected_sentiment with the opposite sign of sentiment_score',
       count(*) FILTER (WHERE (detected_sentiment IN ('Positivo', 'Muy Positivo') AND sentiment_score < 0)
                           OR (detected_sentiment IN ('Negativo', 'Muy Negativo') AND sentiment_score > 0)),
       count(*) FILTER (WHERE detected_sentiment IS NOT NULL AND sentiment_score IS NOT NULL) FROM call_center_interactions
UNION ALL SELECT 'call_center_interactions', 'R06', 'was_resolved null',
       count(*) FILTER (WHERE was_resolved IS NULL), count(*) FROM call_center_interactions

UNION ALL SELECT 'satisfaction_surveys', 'R10', 'CSAT main_score outside [1, 5]',
       count(*) FILTER (WHERE main_score NOT BETWEEN 1 AND 5), count(main_score) FILTER (WHERE survey_type = 'CSAT')
       FROM satisfaction_surveys WHERE survey_type = 'CSAT'
UNION ALL SELECT 'satisfaction_surveys', 'R11', 'NPS main_score outside [0, 10]',
       count(*) FILTER (WHERE main_score NOT BETWEEN 0 AND 10), count(main_score)
       FROM satisfaction_surveys WHERE survey_type = 'NPS'
UNION ALL SELECT 'satisfaction_surveys', 'R12', 'CES main_score outside [1, 7]',
       count(*) FILTER (WHERE main_score NOT BETWEEN 1 AND 7), count(main_score)
       FROM satisfaction_surveys WHERE survey_type = 'CES'
UNION ALL SELECT 'satisfaction_surveys', 'R13', 'nps_category inconsistent with main_score (Detractor 0-6, Passive 7-8, Promoter 9-10)',
       count(*) FILTER (WHERE (nps_category = 'Detractor' AND main_score > 6)
                           OR (nps_category = 'Passive' AND main_score NOT BETWEEN 7 AND 8)
                           OR (nps_category = 'Promoter' AND main_score < 9)),
       count(*) FILTER (WHERE nps_category IS NOT NULL AND main_score IS NOT NULL)
       FROM satisfaction_surveys WHERE survey_type = 'NPS'
UNION ALL SELECT 'satisfaction_surveys', 'R14', 'nps_category present in a survey that is not NPS',
       count(*) FILTER (WHERE survey_type <> 'NPS' AND nps_category IS NOT NULL), count(*) FILTER (WHERE survey_type <> 'NPS')
       FROM satisfaction_surveys
UNION ALL SELECT 'satisfaction_surveys', 'R15', 'response_time_hours < 0',
       count(*) FILTER (WHERE response_time_hours < 0), count(response_time_hours) FROM satisfaction_surveys
UNION ALL SELECT 'satisfaction_surveys', 'R16', 'survey_date outside the window',
       count(*) FILTER (WHERE survey_date < TIMESTAMP '2023-06-17' OR survey_date >= TIMESTAMP '2026-06-18'),
       count(survey_date) FROM satisfaction_surveys

UNION ALL SELECT 'complaints', 'R20', 'creation_date outside the window',
       count(*) FILTER (WHERE creation_date < TIMESTAMP '2023-06-17' OR creation_date >= TIMESTAMP '2026-06-18'),
       count(creation_date) FROM complaints
UNION ALL SELECT 'complaints', 'R21', 'resolution_days < 0',
       count(*) FILTER (WHERE resolution_days < 0), count(resolution_days) FROM complaints
UNION ALL SELECT 'complaints', 'R22', 'resolution_date before creation_date',
       count(*) FILTER (WHERE resolution_date < creation_date), count(*) FILTER (WHERE resolution_date IS NOT NULL AND creation_date IS NOT NULL) FROM complaints
UNION ALL SELECT 'complaints', 'R23', 'first_response_date before creation_date',
       count(*) FILTER (WHERE first_response_date < creation_date), count(*) FILTER (WHERE first_response_date IS NOT NULL AND creation_date IS NOT NULL) FROM complaints
UNION ALL SELECT 'complaints', 'R24', 'assignment_date before creation_date',
       count(*) FILTER (WHERE assignment_date < creation_date), count(*) FILTER (WHERE assignment_date IS NOT NULL AND creation_date IS NOT NULL) FROM complaints
UNION ALL SELECT 'complaints', 'R25', 'closing_date before resolution_date',
       count(*) FILTER (WHERE closing_date < resolution_date), count(*) FILTER (WHERE closing_date IS NOT NULL AND resolution_date IS NOT NULL) FROM complaints
UNION ALL SELECT 'complaints', 'R26', 'status Resolved/Closed without resolution_date',
       count(*) FILTER (WHERE resolution_date IS NULL), count(*) FROM complaints WHERE status IN ('Resolved', 'Closed')
UNION ALL SELECT 'complaints', 'R27', 'open status (Open/In Process/Escalated/Rejected) with resolution_date',
       count(*) FILTER (WHERE resolution_date IS NOT NULL), count(*) FROM complaints WHERE status IN ('Open', 'In Process', 'Escalated', 'Rejected')
UNION ALL SELECT 'complaints', 'R28', 'resolution_days different from resolution_date - creation_date',
       count(*) FILTER (WHERE resolution_days <> date_diff('day', creation_date, resolution_date)),
       count(*) FILTER (WHERE resolution_days IS NOT NULL AND resolution_date IS NOT NULL) FROM complaints
UNION ALL SELECT 'complaints', 'R29', 'claimed_amount <= 0',
       count(*) FILTER (WHERE claimed_amount <= 0), count(claimed_amount) FROM complaints
UNION ALL SELECT 'complaints', 'R30', 'compensation_granted > claimed_amount',
       count(*) FILTER (WHERE compensation_granted > claimed_amount), count(*) FILTER (WHERE compensation_granted IS NOT NULL AND claimed_amount IS NOT NULL) FROM complaints
UNION ALL SELECT 'complaints', 'R31', 'compensation_granted on a case that is not resolved/closed',
       count(*) FILTER (WHERE status NOT IN ('Resolved', 'Closed')), count(*) FROM complaints WHERE compensation_granted IS NOT NULL
UNION ALL SELECT 'complaints', 'R32', 'claimed_amount without currency',
       count(*) FILTER (WHERE currency IS NULL), count(*) FROM complaints WHERE claimed_amount IS NOT NULL

UNION ALL SELECT 'transactions', 'R40', 'amount <= 0',
       count(*) FILTER (WHERE amount <= 0), count(amount) FROM transactions
UNION ALL SELECT 'transactions', 'R41', 'transaction_date outside the window',
       count(*) FILTER (WHERE transaction_date < TIMESTAMP '2023-06-17' OR transaction_date >= TIMESTAMP '2026-06-18'),
       count(transaction_date) FROM transactions
UNION ALL SELECT 'transactions', 'R42', 'fraud_score outside [0, 100]',
       count(*) FILTER (WHERE fraud_score NOT BETWEEN 0 AND 100), count(fraud_score) FROM transactions
UNION ALL SELECT 'transactions', 'R43', 'currency USD with null amount_usd (should be = amount)',
       count(*) FILTER (WHERE amount_usd IS NULL), count(*) FROM transactions WHERE currency = 'USD'
UNION ALL SELECT 'transactions', 'R44', 'currency COP/ARS with null amount_usd',
       count(*) FILTER (WHERE amount_usd IS NULL), count(*) FROM transactions WHERE currency IN ('COP', 'ARS')
UNION ALL SELECT 'transactions', 'R45', 'transaction_status Declined with response_code 00 (approved)',
       count(*) FILTER (WHERE response_code = '00'), count(*) FILTER (WHERE response_code IS NOT NULL)
       FROM transactions WHERE transaction_status = 'Declined'
UNION ALL SELECT 'transactions', 'R46', 'transaction_status Approved with response_code other than 00',
       count(*) FILTER (WHERE response_code <> '00'), count(*) FILTER (WHERE response_code IS NOT NULL)
       FROM transactions WHERE transaction_status = 'Approved'
UNION ALL SELECT 'transactions', 'R47', 'transaction_country written "Mexico" (no accent) instead of "México"',
       count(*) FILTER (WHERE transaction_country = 'Mexico'), count(*) FILTER (WHERE transaction_country IN ('Mexico', 'México'))
       FROM transactions

UNION ALL SELECT 'customers', 'R50', 'credit_score outside [300, 850]',
       count(*) FILTER (WHERE credit_score NOT BETWEEN 300 AND 850), count(credit_score) FROM customers
UNION ALL SELECT 'customers', 'R51', 'last_updated after the end of the dataset (2026-06-17)',
       count(*) FILTER (WHERE last_updated >= TIMESTAMP '2026-06-18'), count(last_updated) FROM customers
UNION ALL SELECT 'customers', 'R52', 'last_updated after the S3 load (2026-08-31): impossible future date',
       count(*) FILTER (WHERE last_updated > TIMESTAMP '2026-08-31 23:59:59'), count(last_updated) FROM customers
UNION ALL SELECT 'customers', 'R53', 'registration_date after last_updated',
       count(*) FILTER (WHERE registration_date > last_updated), count(*) FILTER (WHERE registration_date IS NOT NULL AND last_updated IS NOT NULL) FROM customers
UNION ALL SELECT 'customers', 'R54', 'under 18 at registration',
       count(*) FILTER (WHERE date_diff('year', date_of_birth, registration_date::DATE) < 18),
       count(*) FILTER (WHERE date_of_birth IS NOT NULL AND registration_date IS NOT NULL) FROM customers
UNION ALL SELECT 'customers', 'R55', 'mobile phone prefix does not match the country (+52 MX, +57 CO, +54 AR)',
       count(*) FILTER (WHERE NOT ((country = 'México' AND mobile_phone LIKE '+52%') OR (country = 'Colombia' AND mobile_phone LIKE '+57%')
                                   OR (country = 'Argentina' AND mobile_phone LIKE '+54%'))),
       count(*) FILTER (WHERE mobile_phone IS NOT NULL AND country IS NOT NULL) FROM customers
UNION ALL SELECT 'customers', 'R56', 'detected_accent does not match the country',
       count(*) FILTER (WHERE NOT ((country = 'México' AND detected_accent = 'mexican') OR (country = 'Colombia' AND detected_accent = 'colombian')
                                   OR (country = 'Argentina' AND detected_accent = 'argentine'))),
       count(*) FILTER (WHERE detected_accent IS NOT NULL AND country IS NOT NULL) FROM customers

UNION ALL SELECT 'products', 'R60', 'last_updated after the end of the dataset (2026-06-17)',
       count(*) FILTER (WHERE last_updated >= TIMESTAMP '2026-06-18'), count(last_updated) FROM products
UNION ALL SELECT 'products', 'R61', 'last_updated after the S3 load (2026-08-31): impossible future date',
       count(*) FILTER (WHERE last_updated > TIMESTAMP '2026-08-31 23:59:59'), count(last_updated) FROM products
UNION ALL SELECT 'products', 'R62', 'last_transaction_date after the end of the dataset',
       count(*) FILTER (WHERE last_transaction_date >= TIMESTAMP '2026-06-18'), count(last_transaction_date) FROM products
UNION ALL SELECT 'products', 'R63', 'opening_date after expiration_date',
       count(*) FILTER (WHERE opening_date > expiration_date), count(*) FILTER (WHERE opening_date IS NOT NULL AND expiration_date IS NOT NULL) FROM products
UNION ALL SELECT 'products', 'R64', 'current_balance < 0',
       count(*) FILTER (WHERE current_balance < 0), count(current_balance) FROM products
UNION ALL SELECT 'products', 'R65', 'Tarjeta Crédito without credit_limit',
       count(*) FILTER (WHERE credit_limit IS NULL), count(*) FROM products WHERE product_type = 'Tarjeta Crédito'
UNION ALL SELECT 'products', 'R66', 'days_past_due on a non-credit product',
       count(*) FILTER (WHERE days_past_due IS NOT NULL), count(*)
       FROM products WHERE product_type IN ('Cuenta Ahorro', 'Cuenta Corriente', 'Tarjeta Débito', 'Inversión', 'Seguro')
UNION ALL SELECT 'products', 'R67', 'last_transaction_date before opening_date',
       count(*) FILTER (WHERE last_transaction_date::DATE < opening_date), count(*) FILTER (WHERE last_transaction_date IS NOT NULL AND opening_date IS NOT NULL) FROM products

UNION ALL SELECT 'branches', 'R70', 'coordinates near (0, 0) (|lat| < 1 and |lon| < 1)',
       count(*) FILTER (WHERE abs(latitude) < 1 AND abs(longitude) < 1), count(*) FILTER (WHERE latitude IS NOT NULL AND longitude IS NOT NULL) FROM branches
UNION ALL SELECT 'branches', 'R71', 'longitude >= 0 (MX/CO/AR are west of Greenwich)',
       count(*) FILTER (WHERE longitude >= 0), count(longitude) FROM branches

UNION ALL SELECT 'digital_events', 'R80', 'event_date outside the window',
       count(*) FILTER (WHERE event_date < TIMESTAMP '2023-06-17' OR event_date >= TIMESTAMP '2026-06-18'), count(event_date) FROM digital_events
UNION ALL SELECT 'digital_events', 'R81', 'duration_seconds < 0',
       count(*) FILTER (WHERE duration_seconds < 0), count(duration_seconds) FROM digital_events
UNION ALL SELECT 'digital_events', 'R82', 'ip_country written "Mexico" (no accent) instead of "México"',
       count(*) FILTER (WHERE ip_country = 'Mexico'), count(*) FILTER (WHERE ip_country IN ('Mexico', 'México')) FROM digital_events

UNION ALL SELECT 'call_transcripts', 'R90', 'accent_confidence outside [0, 1]',
       count(*) FILTER (WHERE accent_confidence NOT BETWEEN 0 AND 1), count(accent_confidence) FROM call_transcripts
UNION ALL SELECT 'call_transcripts', 'R91', 'agent_text with an unfilled placeholder ({monto}, {moneda}, {limite}, ...)',
       count(*) FILTER (WHERE regexp_matches(agent_text, '\{[a-z_]+\}')), count(agent_text) FROM call_transcripts
UNION ALL SELECT 'call_transcripts', 'R92', 'full_text with an unfilled placeholder',
       count(*) FILTER (WHERE regexp_matches(full_text, '\{[a-z_]+\}')), count(full_text) FROM call_transcripts
UNION ALL SELECT 'call_transcripts', 'R93', 'detected_language other than es',
       count(*) FILTER (WHERE detected_language <> 'es'), count(detected_language) FROM call_transcripts
