-- Supports: W2 dossier §(7) and findings.md §9 (optional exploration: do people call because the app failed?).
-- Produces: outputs/tables/06_digital_funnel.csv (via eda/funnel.py).
-- For each contact: did the same customer have Error / Login events in the previous 24 h? Control: the same
-- 24 h window but 7 days earlier (the customer's normal activity). Only events with customer_id (76% of the total).
-- {case_int} = interactions rules.
WITH e AS (
    SELECT customer_id, event_date, event_type = 'Error' AS is_error, event_type = 'Login' AS is_login
    FROM digital_events WHERE customer_id IS NOT NULL AND event_type IN ('Error', 'Login')
),
i AS (SELECT interaction_id, customer_id, interaction_date, reason_category, {case_int} AS rule_int
      FROM call_center_interactions),
pre AS (
    SELECT i.interaction_id, bool_or(e.is_error) AS err, bool_or(e.is_login) AS login
    FROM i JOIN e ON e.customer_id = i.customer_id
         AND e.event_date >= i.interaction_date - INTERVAL 24 HOUR AND e.event_date < i.interaction_date
    GROUP BY 1
),
ctl AS (
    SELECT i.interaction_id, bool_or(e.is_error) AS err, bool_or(e.is_login) AS login
    FROM i JOIN e ON e.customer_id = i.customer_id
         AND e.event_date >= i.interaction_date - INTERVAL 8 DAY AND e.event_date < i.interaction_date - INTERVAL 7 DAY
    GROUP BY 1
)
SELECT i.reason_category, i.rule_int, count(*) AS n,
       count(*) FILTER (WHERE coalesce(pre.err, FALSE)) AS n_error_24h_before,
       count(*) FILTER (WHERE coalesce(ctl.err, FALSE)) AS n_error_control,
       count(*) FILTER (WHERE coalesce(pre.login, FALSE)) AS n_login_24h_before,
       count(*) FILTER (WHERE coalesce(ctl.login, FALSE)) AS n_login_control
FROM i LEFT JOIN pre USING (interaction_id) LEFT JOIN ctl USING (interaction_id)
WHERE i.interaction_date >= TIMESTAMP '2023-06-25'   -- leaves 8 days of history for the control window
GROUP BY ALL
ORDER BY n DESC
