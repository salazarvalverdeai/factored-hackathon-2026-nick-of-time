-- Respalda: findings.md §2 y mapeo_workflows.md (¿category, subcategory y case_type son coherentes entre sí?).
-- Produce: outputs/tables/02_complaints_crosstab.csv (vía eda/demand.py).
SELECT case_type, category, coalesce(subcategory, '(nulo)') AS subcategory, count(*) AS n,
       round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY category), 2) AS pct_within_category
FROM complaints
GROUP BY case_type, category, coalesce(subcategory, '(nulo)')
ORDER BY category, n DESC
