-- Supports: workflow_mapping.md and findings.md §3 (coverage by rule, source, workflow and confidence).
-- Produces: outputs/tables/03_coverage_by_rule.csv (via eda/workflows.py).
-- Template: {case_expr} = CASE WHEN <condition> THEN '<rule_id>' ... END built from 03_workflow_mapping.csv
-- in priority order (the first rule that matches wins); {source} = block from 03_mapping_sources.sql.
SELECT {case_expr} AS rule_id, count(*) AS n
FROM ({source}) s
GROUP BY 1
