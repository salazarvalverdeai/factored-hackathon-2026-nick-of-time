-- Supports: data_quality.md §B3 (FK orphans).
-- Produces: outputs/tables/01_fk_orphans.csv (via eda/quality.py, which fills in {child}, {fk}, {parent}, {parent_pk}).
-- Denominator: child rows with a non-null FK. Orphan = non-null FK with no row in the parent table.
SELECT count(c."{fk}")                                          AS n_with_fk,
       count(*) - count(c."{fk}")                               AS n_fk_null,
       count(c."{fk}") FILTER (WHERE p.pk IS NULL)              AS n_orphans
FROM {child} c
LEFT JOIN (SELECT DISTINCT "{parent_pk}" AS pk FROM {parent}) p ON c."{fk}" = p.pk
