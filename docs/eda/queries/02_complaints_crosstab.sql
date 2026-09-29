-- Supports: findings.md §2 and workflow_mapping.md (are category, subcategory and case_type consistent with each other?).
-- Produces: outputs/tables/02_complaints_crosstab.csv (via eda/demand.py).
SELECT case_type, category, coalesce(subcategory, '(nulo)') AS subcategory, count(*) AS n,
       round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY category), 2) AS pct_within_category
FROM complaints
GROUP BY case_type, category, coalesce(subcategory, '(nulo)')
ORDER BY category, n DESC
