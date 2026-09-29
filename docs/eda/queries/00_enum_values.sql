-- Supports: findings.md §0 / data_quality.md (actual enum values, differences from the data dictionary).
-- Produces: outputs/tables/00_enum_values.csv (via eda/inventory.py, which fills in {table} and {column} for each
-- VARCHAR/BOOLEAN column with <= 100 distinct values). NULL is reported as one more value.
-- Concrete example: replace {table} with call_center_interactions and {column} with reason_category.
SELECT "{column}"                                             AS value,
       count(*)                                               AS n,
       round(100.0 * count(*) / sum(count(*)) OVER (), 3)     AS pct,
       count(*) OVER ()                                       AS n_distinct
FROM {table}
GROUP BY 1
ORDER BY n DESC
