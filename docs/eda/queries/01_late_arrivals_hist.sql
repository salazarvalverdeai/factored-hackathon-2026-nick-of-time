-- Respalda: calidad_datos.md §B4 (distribución del rezago por día, para ver la forma de la cola).
-- Produce: outputs/tables/01_late_arrivals_hist.csv (vía eda/quality.py, misma {source} que 01_late_arrivals.sql).
-- Los rezagos > 60 días o < -7 se agrupan en los extremos.
SELECT greatest(least(date_diff('day', event_ts::DATE, process_date), 60), -7) AS lag_days_capped,
       count(*)                                                                AS n
FROM {source}
WHERE event_ts IS NOT NULL
GROUP BY 1
ORDER BY 1
