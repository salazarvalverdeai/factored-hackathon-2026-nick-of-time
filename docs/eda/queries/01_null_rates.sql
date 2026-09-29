-- Supports: data_quality.md §B2 (nulls per column) and §B6 (monthly null drift).
-- Produces: outputs/tables/01_null_rates.csv and 01_null_drift.csv (via eda/quality.py).
-- Template: eda/quality.py fills in {table}, {group_expr} ('all' or the partition_date month) and {null_counts}
-- (one `count(*) - count("col") AS "col"` expression per column).
SELECT {group_expr} AS grp,
       count(*)     AS n_rows,
       {null_counts}
FROM {table}
GROUP BY 1
