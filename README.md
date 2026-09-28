# factored-hackathon-2026-contrareloj

Factored AI & Data Hackathon 2026, equipo Contrarreloj. Dataset sintético LATAM Bank (MX, CO, AR; jun 2023 – jun 2026).

## Qué hay
| Carpeta | Contenido |
|---|---|
| `contracts/gold_contract.md` | Contrato de gold: 12 meses de transactions, `customer_id` resuelto por join, `is_fraud` solo en `gold_eval/`, tablas derivadas `customer_profile` y `transactions_enriched` |
| `data/pipeline/` | Pipeline bronze → silver → gold (DuckDB). Contratos de silver en `contracts.py` (pandera) |
| `data/fixtures/late_arrival/` | Fixture sintético de llegadas tardías y cambio de schema (IDs `FX-`) |
| `data/quality_report.md` | Reporte de calidad generado por el pipeline (no se edita a mano) |
| `data/gold/manifest.json` | Versión, fecha, filas y sha256 de cada tabla de `data/gold/` y `data/gold_eval/` (los Parquet no entran a git) |
| `docs/eda/` | EDA: índice en `docs/eda/README.md`, expedientes por workflow, calidad de datos, mapeo, notas del pipeline |
| `queries/pitch/` | Queries de verificación de los números del pitch y su salida (copia del repo del EDA) |
| `tests/` | pytest sin red: contratos, check de pertenencia al cliente y fixture de punta a punta |

## Cómo se reproduce
```bash
cp .env.example .env       # completar las credenciales S3 (diccionario de datos de Factored, pág. 2)
make setup                 # venv + dependencias + pipeline desde S3 + fixture + data/quality_report.md
make test                  # pytest, sin red
```
`make setup SOURCE=local` corre sobre un espejo local ya descargado en `data/<tabla>/` (sin red). Las credenciales
viven solo en `.env`, que no entra a git.
