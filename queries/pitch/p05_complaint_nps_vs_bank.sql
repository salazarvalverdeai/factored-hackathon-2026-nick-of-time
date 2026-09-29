-- Número del pitch: "NPS −85.3" (contactos Queja) vs −74.5 del banco.
-- Respaldo EDA: outputs/tables/04_workflow_scorecard.csv (W3_disputas y TODOS, métrica nps), vía
--   docs/eda/queries/04_interactions_base.sql + eda/outcomes.py; escala en 01_survey_scale_usage.csv.
-- NPS = % promotores (9–10) − % detractores (0–6) sobre encuestas survey_type = 'NPS' unidas por interaction_id.
-- En el dataset no hay respuestas 8–10 (escala observada 2–7), así que NPS = −% detractores.
WITH s AS (
    SELECT i.reason_category, s.main_score
    FROM satisfaction_surveys s JOIN call_center_interactions i USING (interaction_id)
    WHERE s.survey_type = 'NPS'
), g AS (
    SELECT 'Queja (W3, INT-02)' AS grupo, * FROM s WHERE reason_category = 'Queja'
    UNION ALL
    SELECT 'Todo el banco', * FROM s
)
SELECT grupo,
       count(main_score)                                       AS n_encuestas_nps,
       count(*) FILTER (WHERE main_score <= 6)                 AS n_detractores,
       count(*) FILTER (WHERE main_score >= 9)                 AS n_promotores,
       min(main_score)                                         AS score_min,
       max(main_score)                                         AS score_max,
       round(100.0 * (count(*) FILTER (WHERE main_score >= 9) - count(*) FILTER (WHERE main_score <= 6))
             / count(main_score), 3)                           AS nps
FROM g
GROUP BY grupo
ORDER BY grupo
