-- Número del pitch: "AHT 7.2 vs 4.9" (pitch_brief.md: "Duración p50 7.2 min vs 4.9 del banco (AHT medio 7.2 min)").
-- Respaldo EDA: mediana = outputs/tables/04_workflow_scorecard.csv (duracion_p50_min; toda la ventana, filas con
--   duración); media (AHT) = outputs/tables/06_cost_by_workflow.csv (aht_mean_min; meses completos 2023-07..2026-05),
--   vía docs/eda/queries/04_interactions_base.sql y 06_cost_base.sql.
-- Se calculan las dos (mediana y media) en las dos ventanas para que quede explícito cuál es cuál.
-- quantile_cont = interpolación lineal, igual que np.quantile en eda/outcomes.py.
WITH i AS (
    SELECT reason_category, duration_seconds / 60.0 AS dur_min,
           interaction_date >= TIMESTAMP '2023-07-01' AND interaction_date < TIMESTAMP '2026-06-01' AS full_month
    FROM call_center_interactions
), g AS (
    SELECT 'Queja (W3, INT-02)' AS grupo, * FROM i WHERE reason_category = 'Queja'
    UNION ALL
    SELECT 'Todo el banco', * FROM i
)
SELECT grupo,
       count(dur_min)                                         AS n_con_duracion,
       round(quantile_cont(dur_min, 0.5), 3)                  AS duracion_p50_min,
       round(avg(dur_min), 3)                                 AS duracion_media_min,
       count(dur_min) FILTER (WHERE full_month)               AS n_con_duracion_meses_completos,
       round(avg(dur_min) FILTER (WHERE full_month), 3)       AS aht_media_min_meses_completos
FROM g
GROUP BY grupo
ORDER BY grupo
