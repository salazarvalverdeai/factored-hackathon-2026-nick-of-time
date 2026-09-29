-- Supports: findings.md §0 / data_quality.md (row counts per table vs the data dictionary, PK duplicates).
-- Produces: outputs/tables/00_row_counts.csv (via eda/inventory.py, which fills in {table}, {pk}, {part_min}, {part_max}).
-- Concrete example:  SELECT count(*), count(DISTINCT (interaction_id)), count(DISTINCT filename),
--                    min(partition_date), max(partition_date) FROM call_center_interactions;
SELECT count(*)                       AS n_rows,
       count(DISTINCT ({pk}))         AS n_distinct_pk,
       count(DISTINCT filename)       AS n_files,
       {part_min}                     AS first_partition,
       {part_max}                     AS last_partition
FROM {table}
