-- Número del pitch: "63.0% requiere seguimiento" (contactos Queja).
-- Respaldo EDA: outputs/tables/04_workflow_scorecard.csv (W3_disputas y TODOS, métrica seguimiento_pct), vía
--   docs/eda/queries/04_interactions_base.sql + eda/outcomes.py. Denominador: interacciones con requires_followup no
--   nulo, toda la ventana. IC95 de Wilson.
WITH g AS (
    SELECT 'Queja (W3, INT-02)' AS grupo,
           count(*) FILTER (WHERE requires_followup) AS k, count(requires_followup) AS n
    FROM call_center_interactions WHERE reason_category = 'Queja'
    UNION ALL
    SELECT 'Todo el banco', count(*) FILTER (WHERE requires_followup), count(requires_followup)
    FROM call_center_interactions
), p AS (SELECT *, k / n::DOUBLE AS ph, 1.96 AS z FROM g)
SELECT grupo, k AS n_con_seguimiento, n AS denominador,
       round(100 * ph, 3) AS seguimiento_pct,
       round(100 * ((ph + z * z / (2 * n)) - z * sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))) / (1 + z * z / n), 3) AS ic95_low,
       round(100 * ((ph + z * z / (2 * n)) + z * sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))) / (1 + z * z / n), 3) AS ic95_high
FROM p
ORDER BY grupo
