-- Supports: data_quality.md §B4 (distribution of the lag by day, to see the shape of the tail).
-- Produces: outputs/tables/01_late_arrivals_hist.csv (via eda/quality.py, same {source} as 01_late_arrivals.sql).
-- Lags > 60 days or < -7 are grouped at the extremes.
SELECT greatest(least(date_diff('day', event_ts::DATE, process_date), 60), -7) AS lag_days_capped,
       count(*)                                                                AS n
FROM {source}
WHERE event_ts IS NOT NULL
GROUP BY 1
ORDER BY 1
