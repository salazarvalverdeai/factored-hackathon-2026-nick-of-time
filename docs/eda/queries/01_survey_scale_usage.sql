-- Respalda: data_quality.md §B5 (uso real de las escalas de encuesta; insumo de la decisión 4: no promediar entre tipos).
-- Produce: outputs/tables/01_survey_scale_usage.csv (vía eda/quality.py).
SELECT survey_type, main_score, count(*) AS n,
       round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY survey_type), 2) AS pct_within_type
FROM satisfaction_surveys
GROUP BY survey_type, main_score
ORDER BY survey_type, main_score
