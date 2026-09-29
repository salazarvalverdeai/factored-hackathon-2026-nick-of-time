-- Supports: findings.md §2 and dossiers §(2) (hourly profile of demand; sizes capacity).
-- Produces: outputs/tables/02_hourly_profile.csv (via eda/demand.py).
SELECT hour(interaction_date) AS hour_of_day, count(*) AS n,
       round(100.0 * count(*) / sum(count(*)) OVER (), 3) AS pct
FROM call_center_interactions
GROUP BY hour(interaction_date)
ORDER BY hour_of_day
