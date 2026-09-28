-- Respalda: findings.md §2 y expedientes §(2) (perfil horario de la demanda; dimensiona capacidad).
-- Produce: outputs/tables/02_hourly_profile.csv (vía eda/demand.py).
SELECT hour(interaction_date) AS hour_of_day, count(*) AS n,
       round(100.0 * count(*) / sum(count(*)) OVER (), 3) AS pct
FROM call_center_interactions
GROUP BY hour(interaction_date)
ORDER BY hour_of_day
