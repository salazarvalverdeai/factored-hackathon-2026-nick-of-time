-- Respalda: data_quality.md §B2 (nulos por columna) y §B6 (deriva mensual de nulos).
-- Produce: outputs/tables/01_null_rates.csv y 01_null_drift.csv (vía eda/quality.py).
-- Plantilla: eda/quality.py rellena {table}, {group_expr} ('all' o el mes de partition_date) y {null_counts}
-- (una expresión `count(*) - count("col") AS "col"` por columna).
SELECT {group_expr} AS grp,
       count(*)     AS n_rows,
       {null_counts}
FROM {table}
GROUP BY 1
