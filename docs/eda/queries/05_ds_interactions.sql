-- Respalda: findings.md §5 y sección (4) de los expedientes (dataset del chequeo de señal aprendible en contactos).
-- Produce: dataset en memoria que eda/labels.py usa para 05_learnable_signal.csv (labels was_escalated,
-- not was_resolved, requires_followup). Features disponibles ANTES o AL INICIO del contacto:
--   motivo (supuesto: se conoce al inicio, p. ej. por IVR), canal, tipo, hora, día, espera (solo Inbound),
--   historia previa del cliente (solo contactos anteriores), cliente y agente (foto única: riesgo marcado).
-- Excluidas por ser posteriores o derivadas de la llamada: duración, sentimiento, acento detectado, has_transcript,
-- avg_csat del agente (agrega outcomes, incluidos futuros).
WITH h AS (
    SELECT interaction_id,
           count(*) OVER w90 AS prev_contacts_90d,
           coalesce(sum(was_escalated::INT) OVER w90, 0) AS prev_escalations_90d,
           coalesce(sum((NOT was_resolved)::INT) OVER w90, 0) AS prev_unresolved_90d,
           date_diff('hour', lag(interaction_date) OVER (PARTITION BY customer_id ORDER BY interaction_date),
                     interaction_date) / 24.0 AS days_since_prev
    FROM call_center_interactions
    WINDOW w90 AS (PARTITION BY customer_id ORDER BY interaction_date
                   RANGE BETWEEN INTERVAL 90 DAY PRECEDING AND INTERVAL 1 SECOND PRECEDING)
)
SELECT i.interaction_date,
       i.was_escalated, i.was_resolved, i.requires_followup,
       i.reason_category, i.channel, i.interaction_type,
       hour(i.interaction_date) AS hour_of_day, isodow(i.interaction_date) AS day_of_week,
       i.wait_time_seconds,
       h.prev_contacts_90d, h.prev_escalations_90d, h.prev_unresolved_90d, h.days_since_prev,
       c.segment, c.country, c.customer_status, c.credit_score, c.estimated_monthly_income,
       date_diff('day', c.registration_date, i.interaction_date) AS customer_tenure_days,
       date_diff('year', c.date_of_birth, i.interaction_date::DATE) AS customer_age,
       a.experience_level AS agent_experience, a.agent_type, a.specialty AS agent_specialty
FROM call_center_interactions i
JOIN h USING (interaction_id)
LEFT JOIN customers c USING (customer_id)
LEFT JOIN service_agents a USING (agent_id)
ORDER BY i.interaction_id  -- orden estable: el ajuste de los modelos depende del orden
