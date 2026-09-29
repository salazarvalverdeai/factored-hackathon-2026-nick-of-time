-- Respalda: data_quality.md §B4 y findings.md §1 (rezago de llegada).
-- Produce: outputs/tables/01_late_arrivals.csv (vía eda/quality.py).
-- Plantilla: eda/quality.py rellena {source}: una subconsulta con columnas event_ts (fecha del evento),
-- process_date y partition_date. Para call_transcripts, event_ts es interaction_date de la interacción asociada.
-- lag_days = process_date - fecha del evento (días calendario). > 0 = llegó tarde; < 0 = procesado antes del evento.
WITH l AS (
    SELECT date_diff('day', event_ts::DATE, process_date)  AS lag_days,
           date_diff('day', process_date, partition_date)  AS partition_minus_process
    FROM {source}
)
SELECT count(*)                                              AS n_rows,
       count(lag_days)                                       AS n_with_lag,
       quantile_cont(lag_days, 0.50)                         AS lag_p50,
       quantile_cont(lag_days, 0.95)                         AS lag_p95,
       quantile_cont(lag_days, 0.99)                         AS lag_p99,
       min(lag_days)                                         AS lag_min,
       max(lag_days)                                         AS lag_max,
       round(100.0 * avg((lag_days < 0)::INT), 3)            AS pct_lag_negative,
       round(100.0 * avg((lag_days = 0)::INT), 3)            AS pct_lag_0,
       round(100.0 * avg((lag_days BETWEEN 1 AND 7)::INT), 3) AS pct_lag_1_7,
       round(100.0 * avg((lag_days BETWEEN 8 AND 30)::INT), 3) AS pct_lag_8_30,
       round(100.0 * avg((lag_days > 30)::INT), 3)           AS pct_lag_gt_30,
       round(100.0 * avg((partition_minus_process <> 0)::INT), 3) AS pct_partition_ne_process_date
FROM l
