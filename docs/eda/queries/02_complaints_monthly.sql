-- Supports: findings.md §2 (complaints by case_type, category, subcategory, reception_channel, per month).
-- Produces: outputs/tables/02_complaints_monthly.csv (via eda/demand.py).
WITH k AS (SELECT strftime(creation_date, '%Y-%m') AS ym, case_type, category,
                  coalesce(subcategory, '(nulo)') AS subcategory, reception_channel FROM complaints)
SELECT 'total' AS dimension, 'total' AS value, ym, count(*) AS n FROM k GROUP BY ym
UNION ALL SELECT 'case_type', case_type, ym, count(*) FROM k GROUP BY case_type, ym
UNION ALL SELECT 'category', category, ym, count(*) FROM k GROUP BY category, ym
UNION ALL SELECT 'subcategory', subcategory, ym, count(*) FROM k GROUP BY subcategory, ym
UNION ALL SELECT 'reception_channel', reception_channel, ym, count(*) FROM k GROUP BY reception_channel, ym
ORDER BY dimension, value, ym
