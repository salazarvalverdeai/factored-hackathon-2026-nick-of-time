-- Respalda: data_quality.md §B4 (el "día" de cada archivo no empieza a medianoche).
-- Produce: outputs/tables/01_day_boundary.csv (vía eda/quality.py).
-- hours_from_partition = horas entre la medianoche de partition_date y la fecha-hora del evento.
WITH e AS (
    SELECT 'call_center_interactions' AS tbl, date_diff('minute', partition_date::TIMESTAMP, interaction_date) / 60.0 AS h FROM call_center_interactions
    UNION ALL SELECT 'complaints', date_diff('minute', partition_date::TIMESTAMP, creation_date) / 60.0 FROM complaints
    UNION ALL SELECT 'transactions', date_diff('minute', partition_date::TIMESTAMP, transaction_date) / 60.0 FROM transactions
    UNION ALL SELECT 'digital_events', date_diff('minute', partition_date::TIMESTAMP, event_date) / 60.0 FROM digital_events
    UNION ALL SELECT 'satisfaction_surveys', date_diff('minute', partition_date::TIMESTAMP, survey_date) / 60.0 FROM satisfaction_surveys
)
SELECT tbl, count(*) AS n, round(min(h), 2) AS min_hours_from_partition, round(max(h), 2) AS max_hours_from_partition,
       round(100.0 * avg((h >= 24)::INT), 2) AS pct_next_calendar_day
FROM e GROUP BY tbl ORDER BY tbl
