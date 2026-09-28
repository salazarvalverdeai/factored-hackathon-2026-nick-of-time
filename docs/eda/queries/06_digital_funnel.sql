-- Respalda: expediente W2 §(7) y findings.md §9 (exploración opcional: ¿la gente llama porque la app falló?).
-- Produce: outputs/tables/06_digital_funnel.csv (vía eda/funnel.py).
-- Para cada contacto: ¿el mismo cliente tuvo eventos Error / Login en las 24 h previas? Control: la misma franja de
-- 24 h pero 7 días antes (actividad normal del cliente). Solo eventos con customer_id (76% del total).
-- {case_int} = reglas de interactions.
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
WHERE i.interaction_date >= TIMESTAMP '2023-06-25'   -- deja 8 días de historia para la ventana de control
GROUP BY ALL
ORDER BY n DESC
