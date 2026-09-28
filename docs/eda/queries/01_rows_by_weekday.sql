-- Respalda: calidad_datos.md §B7 y la hipótesis de la fase 0 (fines de semana a la mitad => conteos = 6/7 del
-- diccionario). Produce: outputs/tables/01_rows_by_weekday.csv (vía eda/quality.py).
-- Día = partition_date (el archivo diario). ratio_vs_weekday = filas por día / promedio de filas por día lun-vie.
WITH d AS (
    SELECT 'call_center_interactions' AS tbl, partition_date, count(*) AS n FROM call_center_interactions GROUP BY ALL
    UNION ALL SELECT 'call_transcripts', partition_date, count(*) FROM call_transcripts GROUP BY ALL
    UNION ALL SELECT 'satisfaction_surveys', partition_date, count(*) FROM satisfaction_surveys GROUP BY ALL
    UNION ALL SELECT 'complaints', partition_date, count(*) FROM complaints GROUP BY ALL
    UNION ALL SELECT 'transactions', partition_date, count(*) FROM transactions GROUP BY ALL
    UNION ALL SELECT 'digital_events', partition_date, count(*) FROM digital_events GROUP BY ALL
),
w AS (
    SELECT tbl, isodow(partition_date) AS dow, dayname(partition_date) AS day_name,
           count(*) AS n_days, sum(n) AS n_rows, avg(n) AS rows_per_day
    FROM d GROUP BY ALL
)
SELECT *, round(rows_per_day / avg(rows_per_day) FILTER (WHERE dow <= 5) OVER (PARTITION BY tbl), 3) AS ratio_vs_weekday
FROM w ORDER BY tbl, dow
