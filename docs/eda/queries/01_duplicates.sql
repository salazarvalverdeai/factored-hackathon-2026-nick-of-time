-- Supports: data_quality.md §B1 and findings.md §1 (duplicates per table).
-- Produces: dup_* columns of outputs/tables/01_quality_summary.csv (via eda/quality.py).
-- Template: eda/quality.py fills in {table} and the column lists:
--   {all_cols}        all columns in the file (without filename or partition_date)
--   {content_cols}    all except the generated identifiers (PK)                 -> "same row, different ID"
--   {content_cols_np} all except PK and process_date                            -> "same event re-delivered on another day"
-- Counted with a 64-bit hash() over the row: with <= 16M rows the collision probability is < 1e-5.
SELECT count(*)                                          AS n_rows,
       count(*) - count(DISTINCT hash({all_cols}))       AS dup_exact,
       count(*) - count(DISTINCT hash({content_cols}))   AS dup_content_excl_pk,
       count(*) - count(DISTINCT hash({content_cols_np})) AS dup_content_excl_pk_process_date
FROM {table}
