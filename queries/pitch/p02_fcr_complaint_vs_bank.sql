-- Pitch number: "FCR 43.6% vs 76.6% for the bank".
-- EDA backing: outputs/tables/04_workflow_scorecard.csv (W3_disputes and ALL, metric fcr_pct), via
--   docs/eda/queries/04_interactions_base.sql + eda/outcomes.py. W3 in contacts = rule INT-02
--   (reason_category = 'Queja', low confidence). FCR = was_resolved over interactions with non-null was_resolved,
--   whole window. Wilson CI95 (same formula as eda/common.py).
WITH g AS (
    SELECT 'Queja (W3, INT-02)' AS group_name,
           count(*) FILTER (WHERE was_resolved) AS k, count(was_resolved) AS n
    FROM call_center_interactions WHERE reason_category = 'Queja'
    UNION ALL
    SELECT 'Whole bank', count(*) FILTER (WHERE was_resolved), count(was_resolved)
    FROM call_center_interactions
), p AS (SELECT *, k / n::DOUBLE AS ph, 1.96 AS z FROM g)
SELECT group_name, k AS n_resolved, n AS denominator,
       round(100 * ph, 3) AS fcr_pct,
       round(100 * ((ph + z * z / (2 * n)) - z * sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))) / (1 + z * z / n), 3) AS ci95_low,
       round(100 * ((ph + z * z / (2 * n)) + z * sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))) / (1 + z * z / n), 3) AS ci95_high
FROM p
ORDER BY group_name
