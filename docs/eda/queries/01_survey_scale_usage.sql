-- Supports: data_quality.md §B5 (actual use of the survey scales; input to decision 4: do not average across types).
-- Produces: outputs/tables/01_survey_scale_usage.csv (via eda/quality.py).
SELECT survey_type, main_score, count(*) AS n,
       round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY survey_type), 2) AS pct_within_type
FROM satisfaction_surveys
GROUP BY survey_type, main_score
ORDER BY survey_type, main_score
