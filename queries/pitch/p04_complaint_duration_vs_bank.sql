-- Pitch number: "AHT 7.2 vs 4.9" (pitch_brief.md: "p50 duration 7.2 min vs 4.9 for the bank (mean AHT 7.2 min)").
-- EDA backing: median = outputs/tables/04_workflow_scorecard.csv (duracion_p50_min; whole window, rows with
--   duration); mean (AHT) = outputs/tables/06_cost_by_workflow.csv (aht_mean_min; full months 2023-07..2026-05),
--   via docs/eda/queries/04_interactions_base.sql and 06_cost_base.sql.
-- Both (median and mean) are computed over both windows to make explicit which is which.
-- quantile_cont = linear interpolation, same as np.quantile in eda/outcomes.py.
WITH i AS (
    SELECT reason_category, duration_seconds / 60.0 AS dur_min,
           interaction_date >= TIMESTAMP '2023-07-01' AND interaction_date < TIMESTAMP '2026-06-01' AS full_month
    FROM call_center_interactions
), g AS (
    SELECT 'Queja (W3, INT-02)' AS group_name, * FROM i WHERE reason_category = 'Queja'
    UNION ALL
    SELECT 'Whole bank', * FROM i
)
SELECT group_name,
       count(dur_min)                                         AS n_with_duration,
       round(quantile_cont(dur_min, 0.5), 3)                  AS duration_p50_min,
       round(avg(dur_min), 3)                                 AS duration_mean_min,
       count(dur_min) FILTER (WHERE full_month)               AS n_with_duration_full_months,
       round(avg(dur_min) FILTER (WHERE full_month), 3)       AS aht_mean_min_full_months
FROM g
GROUP BY group_name
ORDER BY group_name
