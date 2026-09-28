-- Respalda: calidad_datos.md §B1 y findings.md §1 (duplicados por tabla).
-- Produce: columnas dup_* de outputs/tables/01_quality_summary.csv (vía eda/quality.py).
-- Plantilla: eda/quality.py rellena {table} y las listas de columnas:
--   {all_cols}        todas las columnas del archivo (sin filename ni partition_date)
--   {content_cols}    todas menos los identificadores generados (PK)            -> "misma fila, otro ID"
--   {content_cols_np} todas menos PK y process_date                              -> "mismo evento re-entregado otro día"
-- Se cuenta con hash() de 64 bits sobre la fila: con <= 16M filas la probabilidad de colisión es < 1e-5.
SELECT count(*)                                          AS n_rows,
       count(*) - count(DISTINCT hash({all_cols}))       AS dup_exact,
       count(*) - count(DISTINCT hash({content_cols}))   AS dup_content_excl_pk,
       count(*) - count(DISTINCT hash({content_cols_np})) AS dup_content_excl_pk_process_date
FROM {table}
