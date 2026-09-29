-- Pitch number: "63.0% require follow-up" (Queja contacts).
-- EDA backing: outputs/tables/04_workflow_scorecard.csv (W3_disputes and ALL, metric seguimiento_pct), via
--   docs/eda/queries/04_interactions_base.sql + eda/outcomes.py. Denominator: interactions with non-null
--   requires_followup, whole window. Wilson CI95.
WITH g AS (
    SELECT 'Queja (W3, INT-02)' AS group_name,
           count(*) FILTER (WHERE requires_followup) AS k, count(requires_followup) AS n
    FROM call_center_interactions WHERE reason_category = 'Queja'
    UNION ALL
    SELECT 'Whole bank', count(*) FILTER (WHERE requires_followup), count(requires_followup)
    FROM call_center_interactions
), p AS (SELECT *, k / n::DOUBLE AS ph, 1.96 AS z FROM g)
SELECT group_name, k AS n_follow_up, n AS denominator,
       round(100 * ph, 3) AS follow_up_pct,
       round(100 * ((ph + z * z / (2 * n)) - z * sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))) / (1 + z * z / n), 3) AS ci95_low,
       round(100 * ((ph + z * z / (2 * n)) + z * sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))) / (1 + z * z / n), 3) AS ci95_high
FROM p
ORDER BY group_name
