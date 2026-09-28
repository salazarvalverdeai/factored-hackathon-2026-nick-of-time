-- Respalda: findings.md §0 / calidad_datos.md (conteos por tabla vs diccionario, duplicados de PK).
-- Produce: outputs/tables/00_row_counts.csv (vía eda/inventory.py, que rellena {table}, {pk}, {part_min}, {part_max}).
-- Ejemplo concreto:  SELECT count(*), count(DISTINCT (interaction_id)), count(DISTINCT filename),
--                    min(partition_date), max(partition_date) FROM call_center_interactions;
SELECT count(*)                       AS n_rows,
       count(DISTINCT ({pk}))         AS n_distinct_pk,
       count(DISTINCT filename)       AS n_files,
       {part_min}                     AS first_partition,
       {part_max}                     AS last_partition
FROM {table}
