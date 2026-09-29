-- Respalda: findings.md §0 / data_quality.md (valores reales de enums, diferencias con el diccionario).
-- Produce: outputs/tables/00_enum_values.csv (vía eda/inventory.py, que rellena {table} y {column} para cada
-- columna VARCHAR/BOOLEAN con <= 100 valores distintos). NULL se reporta como un valor más.
-- Ejemplo concreto: reemplazar {table} por call_center_interactions y {column} por reason_category.
SELECT "{column}"                                             AS value,
       count(*)                                               AS n,
       round(100.0 * count(*) / sum(count(*)) OVER (), 3)     AS pct,
       count(*) OVER ()                                       AS n_distinct
FROM {table}
GROUP BY 1
ORDER BY n DESC
