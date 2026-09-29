-- Pitch number: "NPS −85.3" (Queja contacts) vs −74.5 for the bank.
-- EDA backing: outputs/tables/04_workflow_scorecard.csv (W3_disputes and ALL, metric nps), via
--   docs/eda/queries/04_interactions_base.sql + eda/outcomes.py; scale in 01_survey_scale_usage.csv.
-- NPS = % promoters (9–10) − % detractors (0–6) over surveys with survey_type = 'NPS' joined on interaction_id.
-- The dataset has no 8–10 responses (observed scale 2–7), so NPS = −% detractors.
WITH s AS (
    SELECT i.reason_category, s.main_score
    FROM satisfaction_surveys s JOIN call_center_interactions i USING (interaction_id)
    WHERE s.survey_type = 'NPS'
), g AS (
    SELECT 'Queja (W3, INT-02)' AS group_name, * FROM s WHERE reason_category = 'Queja'
    UNION ALL
    SELECT 'Whole bank', * FROM s
)
SELECT group_name,
       count(main_score)                                       AS n_nps_surveys,
       count(*) FILTER (WHERE main_score <= 6)                 AS n_detractors,
       count(*) FILTER (WHERE main_score >= 9)                 AS n_promoters,
       min(main_score)                                         AS score_min,
       max(main_score)                                         AS score_max,
       round(100.0 * (count(*) FILTER (WHERE main_score >= 9) - count(*) FILTER (WHERE main_score <= 6))
             / count(main_score), 3)                           AS nps
FROM g
GROUP BY group_name
ORDER BY group_name
