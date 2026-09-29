# David · pipeline, calidad, presentación del repo

Entrego el gold que leen las tools y la evidencia de data engineering: contratos, checks con conteos, manifest, fixtures y un `make setup` que reproduce todo desde un clon limpio.

Flujo (recibo → construyo → entrego): S3 crudo (13 tablas, 941 MB), `gold_contract.md` (Freddy), lista de KPIs del pitch (Diego), EDA y queries ya hechos → bronze fiel + silver con contratos, gold Parquet + manifest + flags `qc_*`, derivadas y fixtures de demo, fixture de llegadas tardías (v2), `make setup`, tests, `docs/eda` ordenado → gold v1 (Freddy, GianMarco), `demo_index.csv` (Diego), `gold_eval` y `gold_analytics`, `/data`, README, repo sin secretos.

## Qué recibo y qué entrego

| Recibo de | Qué | Para |
| --- | --- | --- |
| Freddy | `gold_contract.md`: tablas base, derivadas, fixtures, qué no debe estar (`is_fraud`) | Saber exactamente qué masticar |
| Diego | Lista de KPIs del pitch para `gold_analytics/kpis_pitch.csv` | Que el tablero lea del gold |

| Entrego a | Qué | Cuándo |
| --- | --- | --- |
| Freddy y GianMarco | Gold v1 (customers, products, transactions 12 m con `customer_id` por join) + `manifest.json` | Mar 29 |
| Freddy y Diego | Derivadas `customer_profile`, `transactions_enriched`, `product_state_snapshot`; fixtures `demo_customers`, `demo_transactions`, `demo_index.csv` | Mié 30 |
| Freddy | `gold_eval/transaction_labels` (solo aquí `is_fraud`) | Jue 1 |
| Diego y GianMarco | `gold_analytics/`; contenido de `/data` (pipeline, checks, manifest, fixture) | Jue 1, Vie 2 |
| Todos | `make setup`, `quality_report.md` generado, `docs/eda/` con índice, README, revisión de secretos | Mar 29, Dom 4 |

## Reglas del gold

`is_fraud` nunca en tablas que lean las tools. Gold es solo lectura: el bloqueo vive en `case_events`, y `get_product_status()` lee primero el estado mutable y después el gold. Nada se borra: las filas con problemas llevan flags `qc_*` y la capa de servicio decide. Los 15 números del pitch se reproducen con `python -m queries.run` y coinciden. Fijar versiones en `requirements.txt` (DuckDB 1.5.5 y 1.5.6 dan sha distintos para el mismo contenido).

## Tareas

| Día | Tarea | Hecho cuando |
| --- | --- | --- |
| Lun 28 | Guardar `docs/eda/pipeline_notes.md`; pipeline, docs/eda, tests y Makefile en el repo nuevo; Databricks lee el bucket o DuckDB; fijar versiones | `make setup` desde un clon limpio con venv nuevo (60 s medidos) |
| Mar 29 | Gold v1 según `gold_contract.md`; manifest v1; push al repo público | La API lo lee; los 15 números se reproducen |
| Mié 30 | Derivadas y fixtures de demo con zona esperada; `demo_index.csv` | Diego escribe casos desde `demo_index.csv` |
| Jue 1 | `gold_eval/`, `gold_analytics/` con `kpis_pitch.csv`, fixture `late_arrival` con manifest v2; casos `missing_data` y `late_arrival` en `eval/` | El reporte muestra el delta v1 → v2 |
| Vie 2 – Dom 4 | Contenido de `/data`; README (qué es real, mock, sintético); revisión del historial de git por secretos | Repo limpio y reproducible |

Viernes debe existir: gold v2 con derivadas y fixtures; `make setup` reproduce; `/data` con contenido.

## Dónde encuentro lo mío
`data/pipeline/` (contracts.py, bronze/silver/gold) · `data/gold/manifest.json`, `data/quality_report.md` · `data/fixtures/` · `docs/eda/` (README índice, pipeline_notes.md) · `queries/pitch/` · `contracts/gold_contract.md`.

## Cambios del lunes en la tarde
- Columnas `split` (`hash(customer_id) mod 10`: 0–6 train, 7 dev, 8–9 held-out) y `period` (`fit` jun-2025 a feb-2026, `measure` mar–may-2026) en `customers` y `transactions`, propagadas a `demo_index.csv`. Regla G6: `gold_eval/` lo lee solo el harness.
- Fijar versiones en `requirements.txt` (DuckDB incluido).
- Push del repo público en cuanto Freddy comparta el nombre final y las cuentas de GitHub; no hay bloqueo de Slack.
