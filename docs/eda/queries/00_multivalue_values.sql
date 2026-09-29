-- Respalda: findings.md §0 / workflow_mapping.md (valores de columnas multivalor: detected_intents, main_topics,
-- detected_keywords, languages). Separa por coma, recorta espacios; pct_rows = % de filas que contienen el valor.
-- Produce: outputs/tables/00_multivalue_values.csv (vía eda/inventory.py, que rellena {table} y {column}).
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
