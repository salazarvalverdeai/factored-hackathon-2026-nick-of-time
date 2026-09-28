-- Respalda: findings.md §2 y la sección (2) de los expedientes (volumen mensual por dimensión).
-- Produce: outputs/tables/02_monthly_volume.csv (vía eda/demand.py).
-- Formato largo: dimensión × valor × mes. full_month = mes completo dentro de la ventana (jul 2023 – may 2026, 35 meses).
-- country y segment vienen de customers (foto única al corte).
WITH i AS (
    SELECT strftime(i.interaction_date, '%Y-%m') AS ym, i.reason_category, i.channel, i.interaction_type,
           c.country, c.segment
    FROM call_center_interactions i LEFT JOIN customers c USING (customer_id)
)
SELECT 'total' AS dimension, 'total' AS value, ym, count(*) AS n FROM i GROUP BY ym
UNION ALL SELECT 'reason_category', reason_category, ym, count(*) FROM i GROUP BY reason_category, ym
UNION ALL SELECT 'channel', channel, ym, count(*) FROM i GROUP BY channel, ym
UNION ALL SELECT 'interaction_type', interaction_type, ym, count(*) FROM i GROUP BY interaction_type, ym
UNION ALL SELECT 'country', country, ym, count(*) FROM i GROUP BY country, ym
UNION ALL SELECT 'segment', segment, ym, count(*) FROM i GROUP BY segment, ym
ORDER BY dimension, value, ym
