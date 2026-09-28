-- Respalda: findings.md §2 ("top contact_reason": solo hay 6 valores, idénticos a reason_category) y mezcla por canal.
-- Produce: outputs/tables/02_reason_summary.csv (vía eda/demand.py).
-- Meses completos: 2023-07 a 2026-05.
WITH i AS (
    SELECT reason_category, channel, strftime(interaction_date, '%Y-%m') AS ym
    FROM call_center_interactions
    WHERE interaction_date >= TIMESTAMP '2023-07-01' AND interaction_date < TIMESTAMP '2026-06-01'
),
m AS (SELECT reason_category, ym, count(*) AS n FROM i GROUP BY ALL)
SELECT m.reason_category,
       sum(m.n)                                             AS n_full_months,
       round(100.0 * sum(m.n) / (SELECT count(*) FROM i), 3) AS pct,
       count(*)                                             AS n_months,
       round(avg(m.n), 1)                                   AS monthly_mean,
       round(stddev_samp(m.n), 1)                           AS monthly_sd,
       round(stddev_samp(m.n) / avg(m.n), 4)                AS monthly_cv,
       min(m.n)                                             AS monthly_min,
       max(m.n)                                             AS monthly_max
FROM m GROUP BY 1 ORDER BY n_full_months DESC
