-- Respalda: findings.md §5 (dataset del chequeo de señal aprendible para sla_breached).
-- Features al momento de crear el caso. Excluidas: status, fechas de asignación/respuesta/resolución, resolution,
-- compensation_granted, resolution_satisfaction (todas posteriores).
WITH h AS (
    SELECT complaint_id,
           count(*) OVER (PARTITION BY customer_id ORDER BY creation_date
                          RANGE BETWEEN INTERVAL 365 DAY PRECEDING AND INTERVAL 1 SECOND PRECEDING) AS prev_complaints_365d
    FROM complaints
)
SELECT k.creation_date, k.sla_breached,
       k.case_type, k.category, coalesce(k.subcategory, '(nulo)') AS subcategory, k.priority, k.reception_channel,
       ln(1 + k.claimed_amount) AS log_claimed_amount, coalesce(k.currency, '(nulo)') AS currency,
       k.is_repeat_complainer::INT AS is_repeat_complainer,
       hour(k.creation_date) AS hour_of_day, isodow(k.creation_date) AS day_of_week, h.prev_complaints_365d,
       c.segment, c.country, c.credit_score
FROM complaints k JOIN h USING (complaint_id) LEFT JOIN customers c USING (customer_id)
ORDER BY k.complaint_id
