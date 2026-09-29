# docs/eda — índice

> Copia del EDA hecha el 28 sep 2026 desde el repo `factored-2026-eda-freddy`. Las rutas que citan los documentos y
> que no están en este repo (`outputs/tables/`, `eda/`, `scripts/`, `docs/context/`, `docs/pitch/`) viven allá, igual
> que el código que regenera las cifras del EDA. ¹ = archivo del repo del EDA.

Este índice ordena y enlaza los documentos del EDA del dataset LATAM Bank (sintético, Factored AI & Data Hackathon
2026) y dice qué archivo respalda cada número que usa el pitch. **No reemplaza ni edita ningún documento del EDA**: las
cifras y su contexto siguen en cada archivo. Etiquetas: `[medido]` sale del dataset con la query indicada,
`[supuesto]` es una asunción con fuente y `[proyectado]` es un cálculo sobre supuestos.

## Orden de lectura

| # | Documento | Para qué sirve | Cómo se produce |
|---|---|---|---|
| 1 | [executive_summary.md](executive_summary.md) | Una página: qué tiene y qué no tiene el dataset, dónde hay señal, ranking de workflows, ideas y preguntas para Slack | a mano, desde `findings.md` |
| 2 | [findings.md](findings.md) | Índice del EDA: resumen por workflow, comparación con la misma vara, ideas, vacíos y decisiones; anexo por fase (§0–§6) | a mano, desde `outputs/tables/` |
| 3 | [workflows/W3_disputes.md](workflows/W3_disputes.md) | Expediente de la idea recomendada (8 secciones: mapeo, demanda, outcomes, labels, costo, vacíos, exploraciones, plantillas) | `python -m eda.report` |
| 4 | [workflows/W1_accounts_payments.md](workflows/W1_accounts_payments.md), [W2_cards.md](workflows/W2_cards.md), [W4_credit.md](workflows/W4_credit.md) | Los otros tres expedientes, con la misma estructura | `python -m eda.report` |
| 5 | [data_quality.md](data_quality.md) | Inventario (fase 0), calidad por tabla (fase 1) y §C: la evidencia de data engineering para el pitch | a mano, desde `outputs/tables/00_*`, `01_*` |
| 6 | [workflow_mapping.md](workflow_mapping.md) | Reglas de mapeo v1 a los 4 workflows, cobertura y % ambiguo por fuente, motivo vs texto | `python -m eda.report` |
| 7 | [eda_plan.md](eda_plan.md) | El plan por fases con el que se hizo todo lo anterior | a mano |
| 8 | `docs/pitch/pitch_brief.md`¹ | Qué necesita cada bloque del pitch y de dónde sale cada número | a mano |

Fuera de `docs/eda/`, pero ligado al EDA:

- [queries/](queries/): las `.sql` del EDA (`NN_tema.sql`, NN = fase 00–06), más las reglas de mapeo versionadas
  [03_workflow_mapping.csv](queries/03_workflow_mapping.csv). Las ejecutan los módulos `eda/*.py` y escriben en
  `outputs/tables/NN_*.csv`.
- [../../queries/pitch/](../../queries/pitch/): una query de verificación por número del pitch, con su CSV de salida.
  La tabla de abajo sale de esas queries.
- [pipeline_notes.md](pipeline_notes.md): decisiones del pipeline y de la verificación de números, y lo que no se
  pudo verificar.
- [../../data/quality_report.md](../../data/quality_report.md): reporte del pipeline bronze → silver → gold. Repite, con
  código de producción, los checks de `data_quality.md` §C que necesita la idea W3.

## Mapa de archivos por fase

| Fase | Módulo | Queries (`docs/eda/queries/`) | Tablas (`outputs/tables/`) | Documento |
|---|---|---|---|---|
| 0 Inventario | `eda.inventory` | `00_*.sql` | `00_*.csv` | `data_quality.md` §A |
| 1 Calidad | `eda.quality` | `01_*.sql` | `01_*.csv` | `data_quality.md` §B–C |
| 2 Demanda | `eda.demand` | `02_*.sql` | `02_*.csv` | `findings.md` §2 |
| 3 Mapeo | `eda.workflows` | `03_*.sql`, `03_workflow_mapping.csv` | `03_*.csv` | `workflow_mapping.md` |
| 4 Outcomes | `eda.outcomes` | `04_*.sql` | `04_*.csv` | `findings.md` §4, expedientes §3 |
| 5 Labels | `eda.labels` | `05_*.sql` | `05_*.csv` | `findings.md` §5, expedientes §4 |
| 6 Costo | `eda.cost`, `eda.funnel` | `06_*.sql` | `06_*.csv` | `findings.md` §6, expedientes §5 |
| 7 Reporte | `eda.report` | — | lee `outputs/tables/` | expedientes, `workflow_mapping.md` |

## Números del pitch y su respaldo

Cada fila tiene dos respaldos independientes. **Verificación**: una query nueva en `queries/pitch/` que recalcula el
número directo desde los datos y deja su salida en un CSV al lado. **EDA**: la query y la tabla que lo produjeron
originalmente. "¿Coincide?" compara el valor recalculado, redondeado a los decimales que usa el pitch, con el literal
del pitch. La columna "Aparece en" busca el literal en los documentos. Todo el bloque lo regenera
`python -m queries.run` en el repo del EDA, que tiene `scripts/db.py` y el caché de datos; aquí la tabla y los CSV de
`queries/pitch/` son la copia de esa corrida.

<!-- BEGIN pitch_numbers: generado por `python -m queries.run`; no editar a mano -->

| # | Número del pitch | En el pitch | Recalculado | ¿Coincide? | Acción en el pitch | Query → CSV (verificación) | Respaldo en el EDA (`docs/eda/queries/` → `outputs/tables/`) | Aparece en | Nota |
|---|---|---:|---:|---|---|---|---|---|---|
| N01 | % de complaints que son W3 (cargos no reconocidos + cobros indebidos) | 36.4 | 36.413 | sí | usar tal cual | [p01_w3_share_complaints.sql](../../queries/pitch/p01_w3_share_complaints.sql) → [p01_w3_share_complaints.csv](../../queries/pitch/p01_w3_share_complaints.csv)<br>col. `pct_w3` | `03_apply_mapping.sql` → `03_coverage_summary.csv` (pct_W3_disputas) | `pitch_brief.md`¹, [findings.md](findings.md) |  |
| N02 | Casos W3 por mes | 679 | 678.9 | sí | usar tal cual | [p01_w3_share_complaints.sql](../../queries/pitch/p01_w3_share_complaints.sql) → [p01_w3_share_complaints.csv](../../queries/pitch/p01_w3_share_complaints.csv)<br>col. `w3_per_month` | `04_complaints_base.sql` → `04_workflow_scorecard.csv` (volumen_mensual_complaints) | `pitch_brief.md`¹, [executive_summary.md](executive_summary.md), [findings.md](findings.md) | Media sobre 35 meses completos; el % de N01 usa toda la ventana. |
| N03 | FCR de contactos `Queja` | 43.6 | 43.6 | sí | usar tal cual | [p02_fcr_complaint_vs_bank.sql](../../queries/pitch/p02_fcr_complaint_vs_bank.sql) → [p02_fcr_complaint_vs_bank.csv](../../queries/pitch/p02_fcr_complaint_vs_bank.csv)<br>col. `fcr_pct`, fila `grupo = Queja (W3, INT-02)` | `04_interactions_base.sql` → `04_workflow_scorecard.csv` (fcr_pct) | `pitch_brief.md`¹, [executive_summary.md](executive_summary.md), [findings.md](findings.md) | IC95 [43.316, 43.884], n = 117,021. Contactos `Queja` → W3 es una regla de confianza baja (INT-02). |
| N04 | FCR de todo el banco | 76.6 | 76.648 | sí | usar tal cual, contra TODOS | [p02_fcr_complaint_vs_bank.sql](../../queries/pitch/p02_fcr_complaint_vs_bank.sql) → [p02_fcr_complaint_vs_bank.csv](../../queries/pitch/p02_fcr_complaint_vs_bank.csv)<br>col. `fcr_pct`, fila `grupo = Todo el banco` | `04_interactions_base.sql` → `04_workflow_scorecard.csv` (TODOS, fcr_pct) | `pitch_brief.md`¹, [executive_summary.md](executive_summary.md), [findings.md](findings.md) | n = 686,296. En `04_workflow_scorecard.csv` la columna W2 da casi lo mismo porque su población es una mezcla aleatoria de motivos; comparar contra TODOS, no contra W2. |
| N05 | % de contactos `Queja` que requiere seguimiento | 63.0 | 62.968 | sí | usar tal cual | [p03_complaint_follow_up.sql](../../queries/pitch/p03_complaint_follow_up.sql) → [p03_complaint_follow_up.csv](../../queries/pitch/p03_complaint_follow_up.csv)<br>col. `seguimiento_pct`, fila `grupo = Queja (W3, INT-02)` | `04_interactions_base.sql` → `04_workflow_scorecard.csv` (seguimiento_pct) | `pitch_brief.md`¹, [findings.md](findings.md) | Banco: 34.832%. |
| N06 | Duración de contactos `Queja` ("AHT 7.2") | 7.2 | 7.183 | sí | usar tal cual | [p04_complaint_duration_vs_bank.sql](../../queries/pitch/p04_complaint_duration_vs_bank.sql) → [p04_complaint_duration_vs_bank.csv](../../queries/pitch/p04_complaint_duration_vs_bank.csv)<br>col. `duracion_p50_min`, fila `grupo = Queja (W3, INT-02)` | `04_interactions_base.sql` → `04_workflow_scorecard.csv` (duracion_p50_min); `06_cost_base.sql` → `06_cost_by_workflow.csv` (aht_mean_min) | `pitch_brief.md`¹, [findings.md](findings.md), [W3_disputes.md](workflows/W3_disputes.md) | Mediana 7.183 min; media (AHT, meses completos) 7.243 min. Las dos redondean a 7.2. |
| N07 | Duración del banco ("vs 4.9") | 4.9 | 4.85 | sí | **cambiar redacción** | [p04_complaint_duration_vs_bank.sql](../../queries/pitch/p04_complaint_duration_vs_bank.sql) → [p04_complaint_duration_vs_bank.csv](../../queries/pitch/p04_complaint_duration_vs_bank.csv)<br>col. `duracion_p50_min`, fila `grupo = Todo el banco` | `04_interactions_base.sql` → `04_workflow_scorecard.csv` (TODOS, duracion_p50_min) | `pitch_brief.md`¹ | **Es la mediana (4.85 min), no el AHT.** El AHT medio del banco es 5.358 min. "AHT 7.2 vs 4.9" compara una media con una mediana: usar "duración mediana 7.183 vs 4.85 min" o "AHT 7.243 vs 5.358 min". |
| N08 | NPS de contactos `Queja` | -85.3 | -85.316 | sí | usar como comparación relativa | [p05_complaint_nps_vs_bank.sql](../../queries/pitch/p05_complaint_nps_vs_bank.sql) → [p05_complaint_nps_vs_bank.csv](../../queries/pitch/p05_complaint_nps_vs_bank.csv)<br>col. `nps`, fila `grupo = Queja (W3, INT-02)` | `04_interactions_base.sql` → `04_workflow_scorecard.csv` (nps) | `pitch_brief.md`¹, [executive_summary.md](executive_summary.md), [findings.md](findings.md), [W3_disputes.md](workflows/W3_disputes.md) | n = 10,821; escala observada 2–7, 0 promotores: NPS = −% detractores. Banco: -74.508. Solo vale como comparación relativa. |
| N09 | Días de resolución p50 de complaints W3 | 16 | 16.0 | sí | usar solo como contexto, no como dolor | [p06_w3_resolution_days.sql](../../queries/pitch/p06_w3_resolution_days.sql) → [p06_w3_resolution_days.csv](../../queries/pitch/p06_w3_resolution_days.csv)<br>col. `resolucion_dias_p50`, fila `grupo = W3 (CMP-01..03)` | `04_complaints_base.sql` → `04_workflow_scorecard.csv` (resolucion_dias_p50) | `pitch_brief.md`¹, [findings.md](findings.md) | Igual al banco (16.0 días): no distingue a W3; n = 5,622 casos resueltos. |
| N10 | Fraudes por mes | 120 | 119.8 | sí | usar tal cual | [p07_fraud_per_month.sql](../../queries/pitch/p07_fraud_per_month.sql) → [p07_fraud_per_month.csv](../../queries/pitch/p07_fraud_per_month.csv)<br>col. `fraudes_por_mes` | `04_trigger_events_monthly.sql` → `04_trigger_events_summary.csv` (TRX-01) | `pitch_brief.md`¹, [findings.md](findings.md) | 4,316 fraudes en total (0.098% de las transacciones); 891 sin `fraud_score`. |
| N11 | Precisión con `fraud_score` ≥ 50 | 100 | 100.0 | sí | usar como "precisión histórica" | [p08_fraud_score_thresholds.sql](../../queries/pitch/p08_fraud_score_thresholds.sql) → [p08_fraud_score_thresholds.csv](../../queries/pitch/p08_fraud_score_thresholds.csv)<br>col. `precision_pct`, fila `threshold = 50` | `05_fraud_score_thresholds.sql` → `05_fraud_score_thresholds.csv` | `pitch_brief.md`¹, [executive_summary.md](executive_summary.md), [findings.md](findings.md) | 1,670 de 1,670 marcadas son fraude. Precisión histórica sobre toda la ventana, no un held-out. |
| N12 | Recall con `fraud_score` ≥ 50 | 48.8 | 48.76 | sí | **aclarar denominador** | [p08_fraud_score_thresholds.sql](../../queries/pitch/p08_fraud_score_thresholds.sql) → [p08_fraud_score_thresholds.csv](../../queries/pitch/p08_fraud_score_thresholds.csv)<br>col. `recall_con_score_pct`, fila `threshold = 50` | `05_fraud_score_thresholds.sql` → `05_fraud_score_thresholds.csv` | `pitch_brief.md`¹, [executive_summary.md](executive_summary.md), [findings.md](findings.md), [W3_disputes.md](workflows/W3_disputes.md) | **Denominador: fraudes con score** (3,425). Sobre todos los fraudes (4,316) el recall es 38.69%. |
| N13 | Precisión con `fraud_score` ≥ 30 | 79.6 | 79.58 | sí | usar tal cual | [p08_fraud_score_thresholds.sql](../../queries/pitch/p08_fraud_score_thresholds.sql) → [p08_fraud_score_thresholds.csv](../../queries/pitch/p08_fraud_score_thresholds.csv)<br>col. `precision_pct`, fila `threshold = 30` | `05_fraud_score_thresholds.sql` → `05_fraud_score_thresholds.csv` | `pitch_brief.md`¹, [findings.md](findings.md), [W3_disputes.md](workflows/W3_disputes.md) |  |
| N14 | Recall con `fraud_score` ≥ 30 | 69.3 | 69.28 | sí | usar tal cual | [p08_fraud_score_thresholds.sql](../../queries/pitch/p08_fraud_score_thresholds.sql) → [p08_fraud_score_thresholds.csv](../../queries/pitch/p08_fraud_score_thresholds.csv)<br>col. `recall_con_score_pct`, fila `threshold = 30` | `05_fraud_score_thresholds.sql` → `05_fraud_score_thresholds.csv` | [executive_summary.md](executive_summary.md), [findings.md](findings.md) | Sobre todos los fraudes: 54.98%. |
| N15 | Transacciones marcadas por mes con ≥ 50 | 45 | 45.1 | sí | **aclarar base mensual** | [p08_fraud_score_thresholds.sql](../../queries/pitch/p08_fraud_score_thresholds.sql) → [p08_fraud_score_thresholds.csv](../../queries/pitch/p08_fraud_score_thresholds.csv)<br>col. `marcadas_por_mes_37`, fila `threshold = 50` | `05_fraud_score_thresholds.sql` → `05_fraud_score_thresholds.csv` (flagged_per_month) | [findings.md](findings.md) | El EDA divide por 37 meses calendario. Con la base de "120 fraudes/mes" (35 meses completos) son 46.3/mes. |

15 de 15 números coinciden al redondear al número de decimales que usa el pitch. Resumen en [pitch_numbers.csv](../../queries/pitch_numbers.csv).

<!-- END pitch_numbers -->

## Cómo regenerar

```bash
make setup     # en este repo: pipeline bronze → silver → gold según contracts/gold_contract.md y data/quality_report.md
```
El EDA completo (`python -m eda.<módulo>`, `outputs/tables/`) y la verificación de números (`python -m queries.run`) se
regeneran en el repo del EDA.
