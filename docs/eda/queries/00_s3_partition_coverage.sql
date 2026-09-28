-- Respalda: findings.md §0 (formato real, estructura de particiones, días faltantes, patrón de tamaño).
-- Entrada: outputs/tables/00_inventory_files.csv (generado por `python scripts/s3_inventory.py`, sin descargar datos).
-- Uso: python -c "from scripts.db import get_con; print(get_con().sql(open('docs/eda/queries/00_s3_partition_coverage.sql').read()))"
--      (DuckDB ejecuta todas las sentencias; la conexión devuelve la última. Para ver cada bloque, correrlos por separado.)

CREATE OR REPLACE VIEW s3_inv AS
SELECT "table" AS tbl, key, ext, size_mb, partition_keys, last_modified,
       CASE WHEN partition_keys IS NOT NULL THEN make_date(
            regexp_extract(key, 'year=(\d{4})', 1)::INT,
            regexp_extract(key, 'month=(\d{2})', 1)::INT,
            regexp_extract(key, 'day=(\d{2})', 1)::INT) END AS part_date,
       strptime(nullif(regexp_extract(key, '_(\d{8})\.csv$', 1), ''), '%Y%m%d')::DATE AS file_date
FROM read_csv_auto('outputs/tables/00_inventory_files.csv');

-- 1. Resumen por tabla: archivos, MB, formatos, rango de particiones, ventana de carga a S3
SELECT tbl, count(*) AS files, round(sum(size_mb), 1) AS mb, string_agg(DISTINCT ext, ',') AS formats,
       min(part_date) AS first_day, max(part_date) AS last_day,
       count(DISTINCT part_date) AS n_days,
       count(*) FILTER (WHERE part_date <> file_date) AS name_vs_partition_mismatch,
       count(*) FILTER (WHERE size_mb = 0) AS empty_files,
       min(last_modified) AS first_upload, max(last_modified) AS last_upload
FROM s3_inv GROUP BY 1 ORDER BY mb DESC;

-- 2. Días sin partición entre 2023-06-17 y 2026-06-17, por tabla particionada
WITH cal AS (SELECT unnest(generate_series(DATE '2023-06-17', DATE '2026-06-17', INTERVAL 1 DAY))::DATE AS d),
     t AS (SELECT DISTINCT tbl FROM s3_inv WHERE part_date IS NOT NULL)
SELECT t.tbl, count(*) AS missing_days, min(cal.d) AS first_missing, max(cal.d) AS last_missing
FROM t CROSS JOIN cal
LEFT JOIN s3_inv i ON i.tbl = t.tbl AND i.part_date = cal.d
WHERE i.key IS NULL GROUP BY 1 ORDER BY 1;

-- 3. Tamaño medio de archivo por día de la semana (proxy de volumen diario, antes de descargar)
SELECT tbl, isodow(part_date) AS dow, dayname(part_date) AS day_name,
       round(avg(size_mb) * 1000) AS avg_kb, count(*) AS files
FROM s3_inv WHERE part_date IS NOT NULL GROUP BY ALL ORDER BY tbl, dow;

-- 4. Tamaño medio de archivo por mes (saltos = posible cambio de volumen o de schema)
SELECT tbl, strftime(part_date, '%Y-%m') AS ym, round(avg(size_mb) * 1000) AS avg_kb,
       round(sum(size_mb), 2) AS mb, count(*) AS files
FROM s3_inv WHERE part_date IS NOT NULL GROUP BY ALL ORDER BY tbl, ym;
