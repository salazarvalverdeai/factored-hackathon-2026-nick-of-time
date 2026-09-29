-- Supports: findings.md §0 / workflow_mapping.md (values of multi-value columns: detected_intents, main_topics,
-- detected_keywords, languages). Splits on commas, trims spaces; pct_rows = % of rows that contain the value.
-- Produces: outputs/tables/00_multivalue_values.csv (via eda/inventory.py, which fills in {table} and {column}).
WITH numbered AS (
    SELECT row_number() OVER () AS rid, "{column}" AS raw_value
    FROM {table}
    WHERE "{column}" IS NOT NULL
),
exploded AS (
    SELECT rid, trim(unnest(string_split(raw_value, ','))) AS value FROM numbered
)
SELECT value,
       count(DISTINCT rid)                                              AS n_rows_with_value,
       round(100.0 * count(DISTINCT rid) / (SELECT count(*) FROM {table}), 3) AS pct_rows,
       count(*) OVER ()                                                 AS n_distinct_values
FROM exploded
GROUP BY 1
ORDER BY 2 DESC
