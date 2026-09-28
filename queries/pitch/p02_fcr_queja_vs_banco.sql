-- Número del pitch: "FCR 43.6% vs 76.6% del banco".
-- Respaldo EDA: outputs/tables/04_workflow_scorecard.csv (W3_disputas y TODOS, métrica fcr_pct), vía
--   docs/eda/queries/04_interactions_base.sql + eda/outcomes.py. W3 en contactos = regla INT-02
--   (reason_category = 'Queja', confianza baja). FCR = was_resolved sobre interacciones con was_resolved no nulo,
--   toda la ventana. IC95 de Wilson (misma fórmula que eda/common.py).
WITH g AS (
    SELECT 'Queja (W3, INT-02)' AS grupo,
           count(*) FILTER (WHERE was_resolved) AS k, count(was_resolved) AS n
    FROM call_center_interactions WHERE reason_category = 'Queja'
    UNION ALL
    SELECT 'Todo el banco', count(*) FILTER (WHERE was_resolved), count(was_resolved)
    FROM call_center_interactions
), p AS (SELECT *, k / n::DOUBLE AS ph, 1.96 AS z FROM g)
SELECT grupo, k AS n_resueltas, n AS denominador,
       round(100 * ph, 3) AS fcr_pct,
       round(100 * ((ph + z * z / (2 * n)) - z * sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))) / (1 + z * z / n), 3) AS ic95_low,
       round(100 * ((ph + z * z / (2 * n)) + z * sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))) / (1 + z * z / n), 3) AS ic95_high
FROM p
ORDER BY grupo
