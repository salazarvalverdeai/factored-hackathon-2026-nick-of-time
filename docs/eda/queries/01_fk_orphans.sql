-- Respalda: data_quality.md §B3 (huérfanos de FK).
-- Produce: outputs/tables/01_fk_orphans.csv (vía eda/quality.py, que rellena {child}, {fk}, {parent}, {parent_pk}).
-- Denominador: filas hijas con la FK no nula. Huérfano = FK no nula sin fila en la tabla padre.
SELECT count(c."{fk}")                                          AS n_with_fk,
       count(*) - count(c."{fk}")                               AS n_fk_null,
       count(c."{fk}") FILTER (WHERE p.pk IS NULL)              AS n_orphans
FROM {child} c
LEFT JOIN (SELECT DISTINCT "{parent_pk}" AS pk FROM {parent}) p ON c."{fk}" = p.pk
