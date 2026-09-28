-- Respalda: mapeo_workflows.md y findings.md §3 (cobertura por regla, fuente, workflow y confianza).
-- Produce: outputs/tables/03_coverage_by_rule.csv (vía eda/workflows.py).
-- Plantilla: {case_expr} = CASE WHEN <condición> THEN '<rule_id>' ... END construido desde 03_workflow_mapping.csv
-- en orden de prioridad (gana la primera regla que se cumple); {source} = bloque de 03_mapping_sources.sql.
SELECT {case_expr} AS rule_id, count(*) AS n
FROM ({source}) s
GROUP BY 1
